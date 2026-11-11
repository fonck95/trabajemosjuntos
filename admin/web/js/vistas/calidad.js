// Calidad de datos: coincidencias por nombre (revisadas en bloque, por grupos), conflictos de cédula, solicitudes de los
// titulares, situaciones reportadas, lugares sin punto y nombres nuevos. Todo dato de la base pasa por `html` (escapado).
import { api } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { SEXOS, SITUACIONES } from '../modelo.js';
import {
  $, $$, aviso, avisoError, confirmar, datosForm, dialogo, fecha, fuentesVisibles, html, icono, insigniaFuente, insigniasFuentes,
  leyendaFuentes, montar, nombreFuente, num, titulo,
} from '../ui.js';
import { elegirPunto } from './comunes.js';
import { url } from '../base.js';

const PESTANAS = [['coincidencias', 'Coincidencias'], ['conflictos', 'Conflictos de cédula'], ['solicitudes', 'Solicitudes'],
  ['situaciones', 'Situaciones'], ['lugares', 'Barrios y veredas'], ['sin', 'Sin reconocer']];
const MOTIVOS_CONFLICTO = { nombre_distinto: 'Misma cédula, otro nombre', cedula_anterior: 'Cédula anterior de una ficha',
  posible_digitacion: 'Posible error de digitación', dictada: 'Cédula dictada al consultor' };
const TIPOS_SOLICITUD = { consulta: 'Consulta', correccion: 'Corrección', supresion: 'Supresión', revocatoria: 'Revocatoria',
  otro: 'Otro', registro: 'Pedido de registro' };
const ESTADOS_SOLICITUD = { pendiente: 'Pendiente', en_tramite: 'En trámite', resuelta: 'Resuelta', rechazada: 'Rechazada' };

// ───────── Coincidencias en bloque (GET /api/coincidencias/grupos y POST /api/coincidencias/lote) ─────────
// Un grupo es un conjunto de fichas unidas por coincidencias pendientes (A~B y B~C forman {A, B, C}): se revisa y se
// resuelve entero, con sus señales a la vista, en vez de par por par.
// [clave, plural del filtro, singular de la tarjeta], en el orden del servidor: de la más segura a la bloqueada
const NIVELES = [['alta', 'Muy probables', 'Muy probable'], ['media', 'Probables', 'Probable'], ['baja', 'Dudosas', 'Dudosa'],
  ['bloqueada', 'Bloqueadas', 'Bloqueada']];
const NIVEL = Object.fromEntries(NIVELES.map(([k, , t]) => [k, t]));
const MOTIVOS_COINCIDENCIA = { cruce_cedula: 'Cruce con la base con cédula', nombre_telefono: 'Nombre y teléfono',
  homonimo: 'Mismo nombre', variante: 'Nombre parecido', reporte: 'Reportada por el equipo', alta_simultanea: 'Alta simultánea' };
const POR_PAGINA_GRUPOS = 25;
// Topes de POST /api/coincidencias/lote (422 si se pasan): grupos por petición, pares por grupo y fichas excluidas
const LOTE_GRUPOS = 50;
const MAX_PARES_GRUPO = 60;
const MAX_EXCLUIR = 20;
// Una tanda de uniones puede pasar de los 30 s de una escritura común: cada unión reasigna y recalcula lo ligado
const ESPERA_LOTE = 120000;
// Filas de la comparación, siempre en este orden y con «—» donde falta: así los datos de las fichas quedan alineados
const FILAS = [['nombre', 'Nombre'], ['cedula', 'Cédula'], ['telefonos', 'Teléfonos'], ['correo', 'Correo'],
  ['direccion', 'Dirección'], ['lugar', 'Barrio o vereda'], ['edad', 'Edad y sexo'], ['fuentes', 'Fuentes'],
  ['tramites', 'Trámites'], ['completitud', 'Completitud']];
// Campos de la vista previa (los mismos que arma el servidor) y los que, si son distintos, pasan a alternos al unir
// (`db._pipeline_fusion`: los que llevan procedencia; el nombre, la cédula y el lugar no dejan alterno)
const CAMPOS_VISTA = ['nombre', 'cedula', 'telefonos', 'correo', 'direccion', 'lugar', 'sexo', 'edad', 'fecha_nacimiento'];
const CON_ALTERNOS = new Set(['correo', 'direccion', 'sexo', 'edad', 'fecha_nacimiento']);

const letraFicha = (i) => (i < 26 ? String.fromCharCode(65 + i) : String(i + 1));
const letrasDe = (g) => new Map(g.miembros.map((m, i) => [m.id, letraFicha(i)]));
const vacio = (v) => v == null || (typeof v === 'string' && !v.trim()) || (Array.isArray(v) && !v.length);
/** Texto comparable: sin tildes, en mayúsculas y con espacios simples (María  Pérez = MARIA PEREZ). */
const comparable = (v) => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/\s+/g, ' ').trim();
const digitos = (v) => String(v ?? '').replace(/\D/g, '');
const pctTexto = (x) => (x == null ? '—' : `${Math.round(x * 100)} %`);
const edadTexto = (v) => (/^\d{1,3}$/.test(String(v)) ? `${v} años` : String(v));
const fechaTexto = (v) => (/^\d{4}-\d{2}-\d{2}/.test(String(v)) ? fecha(String(v).slice(0, 10)) : String(v));
const sexoTexto = (v) => SEXOS[v] || String(v);
const plural = (n, uno, varios) => `${num(n)} ${n === 1 ? uno : varios}`;
const sinMovimiento = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/** La fuente que la procedencia de la ficha anota para un campo (el contrato la manda como texto; se acepta también
 * `{fuente}`), o null. */
function procedenciaDe(m, campo) {
  const f = m.procedencia?.[campo];
  return (f && typeof f === 'object' ? f.fuente : f) || null;
}
/** Fuente de un dato de una ficha del grupo: la de su procedencia o, si no tiene, la fuente con que nació la ficha
 * (la misma regla de la vista previa del servidor). */
const fuenteDato = (m, campo) => procedenciaDe(m, campo) || m.fuentes?.[0] || null;

/** La ficha que se conserva por defecto, como el servidor (`destino_de`): la única con cédula; si ninguna o varias, la
 * más completa; a igual completitud, la de menor id (estable). */
function destinoPorDefecto(ms) {
  const conCedula = ms.filter((m) => m.cedula);
  if (conCedula.length === 1) return conCedula[0].id;
  return [...ms].sort((a, b) => (b.completitud || 0) - (a.completitud || 0) || a.id - b.id)[0]?.id ?? null;
}
/** Orden en que se unen: la conservada primero y después las demás por (tiene cédula, completitud), de mayor a menor. */
function ordenUnion(ms, destino) {
  const resto = ms.filter((m) => m.id !== destino)
    .sort((a, b) => (!!b.cedula - !!a.cedula) || (b.completitud || 0) - (a.completitud || 0) || a.id - b.id);
  const d = ms.find((m) => m.id === destino);
  return d ? [d, ...resto] : resto;
}

/** Lo que quedaría en la ficha unida, campo por campo, con la elección hecha en la pantalla (otra ficha conservada o
 * fichas excluidas): una copia aproximada de la `vista_previa` del servidor. Queda el valor de la conservada si lo
 * tiene y si no el primero en el orden de unión; lo distinto pasa a alternos (en los campos que los llevan); los
 * teléfonos se juntan todos. */
function vistaPreviaLocal(ms, destino) {
  const orden = ordenUnion(ms, destino);
  const out = {};
  for (const campo of CAMPOS_VISTA) {
    if (campo === 'telefonos') {
      const numeros = [...new Set(orden.flatMap((m) => m.telefonos || []))];
      const de = orden.find((m) => (m.telefonos || []).length);
      out[campo] = { campo, valor: numeros.length ? numeros.join(', ') : null, fuente: de ? procedenciaDe(de, campo) : null,
        de: de?.id ?? null, otros: [] };
      continue;
    }
    const con = orden.filter((m) => !vacio(m[campo]));
    const queda = con[0];
    const vistos = new Set(queda ? [comparable(queda[campo])] : []);
    const otros = [];
    for (const m of CON_ALTERNOS.has(campo) ? con.slice(1) : []) {
      const k = comparable(m[campo]);
      if (vistos.has(k)) continue;
      vistos.add(k);
      otros.push({ valor: String(m[campo]), fuente: fuenteDato(m, campo), de: m.id });
    }
    out[campo] = queda ? { campo, valor: String(queda[campo]), fuente: fuenteDato(queda, campo), de: queda.id, otros }
      : { campo, valor: null, fuente: null, de: null, otros: [] };
  }
  return out;
}
/** La vista previa que se muestra: la del servidor mientras la elección sea la suya (su ficha conservada, ninguna
 * excluida); si no, la calculada aquí, marcada como estimada. */
function vistaDe(g, e) {
  if (e.conservar === g.destino && !e.excluir.size && Array.isArray(g.vista_previa) && g.vista_previa.length) {
    return { ...Object.fromEntries(g.vista_previa.map((v) => [v.campo, v])), estimada: false };
  }
  return { ...vistaPreviaLocal(incluidas(g, e), e.conservar), estimada: true };
}

const incluidas = (g, e) => g.miembros.filter((m) => !e.excluir.has(m.id));
const cedulasDistintas = (ms) => new Set(ms.map((m) => digitos(m.cedula)).filter(Boolean)).size > 1;

/** ¿Las fichas incluidas siguen unidas entre ellas por pares del grupo? (unión de conjuntos sobre los pares cuyas dos
 * fichas quedan). Sin eso la unión en estrella juntaría fichas que nadie propuso juntar. */
function conexas(g, e) {
  const ids = incluidas(g, e).map((m) => m.id);
  const padre = new Map(ids.map((i) => [i, i]));
  const raiz = (x) => { while (padre.get(x) !== x) x = padre.get(x); return x; };
  for (const p of g.pares) if (padre.has(p.a) && padre.has(p.b)) padre.set(raiz(p.a), raiz(p.b));
  return new Set(ids.map(raiz)).size <= 1;
}

/** Por qué el grupo no se puede unir tal como está en la pantalla, o null. Se vuelve a evaluar al marcar «No es la
 * misma»: un grupo bloqueado por dos cédulas se desbloquea al excluir la que sobra. El servidor valida todo otra vez. */
function bloqueoUnir(g, e) {
  if (g.pares.length > MAX_PARES_GRUPO) {
    return `Tiene ${num(g.pares.length)} pares, más de los ${MAX_PARES_GRUPO} que se resuelven de una vez: únalas desde cada ficha.`;
  }
  if (e.excluir.size > MAX_EXCLUIR) return `Se pueden excluir hasta ${MAX_EXCLUIR} fichas por grupo.`;
  const inc = incluidas(g, e);
  if (inc.length < 2) return 'Queda una sola ficha: no hay nada que unir.';
  if (cedulasDistintas(inc)) return 'Tienen cédulas distintas: marque «No es la misma» en la ficha que sobra.';
  if (!conexas(g, e)) return 'Sin la ficha excluida, las demás no tienen una coincidencia directa: únalas por separado.';
  // Bloqueada sin dos cédulas: un par del grupo ya se había marcado como personas distintas (lo dice el aviso)
  if (g.nivel === 'bloqueada' && !cedulasDistintas(g.miembros) && !e.excluir.size) {
    return 'Antes se marcaron como personas distintas: marque «No es la misma» en la ficha que no corresponde.';
  }
  return null;
}
const bloqueoSeparar = (g) => (g.pares.length > MAX_PARES_GRUPO
  ? `Tiene ${num(g.pares.length)} pares, más de los ${MAX_PARES_GRUPO} que se resuelven de una vez.` : null);

/** Lo que va al servidor por un grupo: sus pares, la decisión y, al unir, la ficha conservada y las excluidas. */
function cuerpoGrupo(g, e, decision) {
  const c = { pares: g.pares.map((p) => p.id), decision };
  if (decision === 'unir') {
    c.conservar = e.conservar;
    if (e.excluir.size) c.excluir = [...e.excluir];
  }
  return c;
}

// Cuántas fichas incluidas tienen cada valor: lo repetido se resalta y lo que choca (cédula, sexo, fecha) se marca
function conteos(inc) {
  const contar = (valores) => {
    const m = new Map();
    for (const v of valores) if (v) m.set(v, (m.get(v) || 0) + 1);
    return m;
  };
  return {
    palabras: contar(inc.flatMap((m) => [...new Set(comparable(m.nombre).split(' ').filter((w) => w.length > 1))])),
    cedula: contar(inc.map((m) => digitos(m.cedula))),
    telefonos: contar(inc.flatMap((m) => [...new Set((m.telefonos || []).map(digitos))])),
    correo: contar(inc.map((m) => comparable(m.correo))),
    direccion: contar(inc.map((m) => comparable(m.direccion))),
    lugar: contar(inc.map((m) => comparable(m.lugar))),
    sexo: contar(inc.map((m) => m.sexo || '')),
    fecha: contar(inc.map((m) => String(m.fecha_nacimiento || '').slice(0, 10))),
    edades: inc.filter((m) => m.edad != null).map((m) => [m.id, Number(m.edad)]),
  };
}

const FALTA = html`<span class="falta" aria-label="Sin dato">—</span>`;

/** Una celda de una ficha: cada valor con la insignia de su fuente; verde si otra ficha incluida lo repite y rojo
 * ondulado si choca (cédula, sexo o fecha distintos, edad a más de 5 años). Las excluidas no se resaltan. */
function celdaFicha(k, m, cu, fuera) {
  const marca = (mapa, v, choque = false) => {
    if (fuera || !v) return '';
    if ((mapa.get(v) || 0) > 1) return 'igual-dato';
    return choque && mapa.size > 1 ? 'choca' : '';
  };
  // El resaltado va solo sobre el valor; la insignia de su fuente, al lado
  const pieza = (texto, clase, fuente) => html`<span class="pieza">${clase ? html`<span class="${clase}">${texto}</span>` : texto}${insigniaFuente(fuente)}</span>`;
  switch (k) {
    case 'nombre': {
      const palabras = String(m.nombre || '').split(/\s+/).filter(Boolean);
      return html`<span class="pieza">${palabras.map((w, i) => html`${i ? ' ' : ''}${!fuera && (cu.palabras.get(comparable(w)) || 0) > 1
        ? html`<span class="igual">${w}</span>` : w}`)}${insigniaFuente(fuenteDato(m, 'nombre'))}</span>`;
    }
    case 'cedula':
      return m.cedula ? pieza(m.cedula, marca(cu.cedula, digitos(m.cedula), true), fuenteDato(m, 'cedula')) : FALTA;
    case 'telefonos': {
      const ts = m.telefonos || [];
      // Cada número puede venir de varias fuentes: solo se pinta la que anote la procedencia
      return ts.length ? html`<span class="piezas">${ts.map((t) => pieza(t, marca(cu.telefonos, digitos(t)), null))}${insigniaFuente(procedenciaDe(m, 'telefonos') || procedenciaDe(m, 'telefono'))}</span>` : FALTA;
    }
    case 'correo': case 'direccion':
      return vacio(m[k]) ? FALTA : pieza(m[k], marca(cu[k], comparable(m[k])), fuenteDato(m, k));
    case 'lugar':
      return vacio(m.lugar) ? FALTA : pieza(titulo(m.lugar), marca(cu.lugar, comparable(m.lugar)), procedenciaDe(m, 'lugar'));
    case 'edad': {
      const ps = [];
      if (m.edad != null) {
        const otras = fuera ? [] : cu.edades.filter(([id]) => id !== m.id).map(([, x]) => Math.abs(x - Number(m.edad)));
        const clase = otras.some((d) => d > 5) ? 'choca' : otras.some((d) => d <= 1) ? 'igual-dato' : '';
        ps.push(pieza(edadTexto(m.edad), clase, fuenteDato(m, 'edad')));
      }
      if (m.fecha_nacimiento) {
        ps.push(pieza(fechaTexto(m.fecha_nacimiento), marca(cu.fecha, String(m.fecha_nacimiento).slice(0, 10), true), fuenteDato(m, 'fecha_nacimiento')));
      }
      if (m.sexo) ps.push(pieza(sexoTexto(m.sexo), marca(cu.sexo, m.sexo, true), fuenteDato(m, 'sexo')));
      return ps.length ? html`<span class="piezas">${ps}</span>` : FALTA;
    }
    case 'fuentes': return insigniasFuentes(m.fuentes) || FALTA;
    case 'tramites': return m.tramites ? num(m.tramites) : FALTA;
    case 'completitud': {
      const c = Number(m.completitud) || 0;
      return html`<span class="barra-comp"><i><b style="width:${c}%"></b></i>${c} %</span>`;
    }
    default: return FALTA;
  }
}

/** La celda «Quedaría»: el valor que queda (con su fuente y la letra de la ficha de donde sale) y cuántos valores
 * distintos pasan a alternos (en `title`, cuáles). */
function celdaQuedaria(k, vp, inc, letras) {
  const pieza = (v, formato = String) => (v && v.valor != null && v.valor !== ''
    ? html`<span class="pieza">${formato(v.valor)}${insigniaFuente(v.fuente)}${v.de != null && letras.has(v.de)
      ? html`<span class="de-ficha" title="Dato de la ficha ${letras.get(v.de)}"><span class="sr">de la ficha </span>${letras.get(v.de)}</span>` : ''}</span>` : '');
  const alternos = (...vs) => {
    const otros = vs.flatMap((v) => v?.otros || []);
    if (!otros.length) return '';
    const cuales = otros.map((o) => `${o.valor} (${nombreFuente(o.fuente) || 'sin fuente'}, ficha ${letras.get(o.de) ?? '?'})`).join('; ');
    return html`<small class="pasan" title="${cuales}">y ${plural(otros.length, 'valor pasa', 'valores pasan')} a alternos</small>`;
  };
  switch (k) {
    case 'fuentes': return insigniasFuentes(inc.flatMap((m) => m.fuentes || [])) || FALTA;
    case 'tramites': {
      const n = inc.reduce((a, m) => a + (Number(m.tramites) || 0), 0);
      return n ? num(n) : FALTA;
    }
    case 'completitud': return html`<span class="falta">Se recalcula al unir</span>`;
    case 'edad': {
      const ps = [pieza(vp.edad, edadTexto), pieza(vp.fecha_nacimiento, fechaTexto), pieza(vp.sexo, sexoTexto)].filter(Boolean);
      return ps.length ? html`<span class="piezas">${ps}</span>${alternos(vp.edad, vp.fecha_nacimiento, vp.sexo)}` : FALTA;
    }
    case 'lugar': return pieza(vp.lugar, titulo) ? html`${pieza(vp.lugar, titulo)}${alternos(vp.lugar)}` : FALTA;
    default: return pieza(vp[k]) ? html`${pieza(vp[k])}${alternos(vp[k])}` : FALTA;
  }
}

/** La grilla de comparación: filas = campos, columnas = fichas (A, B, C…) y, al final, lo que quedaría. */
function tablaComparar(g, e, letras) {
  const inc = incluidas(g, e);
  const vp = vistaDe(g, e);
  const cu = conteos(inc);
  const fuera = (m) => e.excluir.has(m.id);
  return html`<table class="comparar" style="--n:${g.miembros.length}">
    <caption class="sr">Datos de cada ficha, campo por campo, y lo que quedaría al unirlas</caption>
    <colgroup><col class="col-rotulo">${g.miembros.map(() => html`<col class="col-ficha">`)}<col class="col-quedaria"></colgroup>
    <thead><tr><td class="esquina"></td>${g.miembros.map((m) => html`<th scope="col" class="ficha-col${fuera(m) ? ' excluida' : ''}" data-id="${m.id}">
        <span class="ficha-id"><span class="letra-ficha" aria-hidden="true">${letras.get(m.id)}</span><a href="/personas/${m.id}" data-ruta title="Abrir la ficha ${m.id}"><span class="sr">Ficha ${letras.get(m.id)}: </span>${m.nombre}</a></span>
        ${m.consentimiento === 'no' ? html`<span class="chip rojo no-autorizo">No autorizó</span>` : ''}${fuera(m) ? html`<span class="chip borde">No se une</span>` : ''}</th>`)}
      <th scope="col" class="quedaria"><span class="quedaria-t">Quedaría</span> <small>${letras.has(e.conservar) ? `Se conserva la ficha ${letras.get(e.conservar)}` : ''}${vp.estimada ? ' · estimado con su elección' : ''}</small>
        ${inc.some((m) => m.consentimiento === 'no') && inc.some((m) => m.consentimiento !== 'no') ? html`<small class="queda-no">Quedará como «No autorizó»: al unir, el no gana.</small>` : ''}</th></tr>
    <tr class="fila-elegir"><th scope="row">Al unir</th>${g.miembros.map((m) => html`<td class="${fuera(m) ? 'excluida' : ''}">
        <label class="opcion-ficha"><input type="radio" name="conservar-${g.clave}" value="${m.id}" data-conservar ${e.conservar === m.id ? 'checked' : ''} ${fuera(m) ? 'disabled' : ''}> Conservar esta</label>
        <label class="opcion-ficha"><input type="checkbox" value="${m.id}" data-excluir ${fuera(m) ? 'checked' : ''}> No es la misma</label></td>`)}<td class="quedaria"></td></tr></thead>
    <tbody>${FILAS.map(([k, rotulo]) => html`<tr data-fila="${k}"><th scope="row">${rotulo}</th>${g.miembros.map((m) => html`<td class="${fuera(m) ? 'excluida' : ''}">${celdaFicha(k, m, cu, fuera(m))}</td>`)}<td class="quedaria">${celdaQuedaria(k, vp, inc, letras)}</td></tr>`)}</tbody>
  </table>`;
}

/** Señales a favor (✓, verdes) y en contra (✕, rojas): las del par si es uno solo; si son varios, una línea por par. */
function senalesGrupo(g, letras) {
  const chips = (p) => html`${(p.a_favor || []).map((s) => html`<span class="senal a-favor" data-senal="${s.clave}">${icono('hecho')}<span class="sr">A favor: </span>${s.texto}</span>`)}${(p.en_contra || []).map((s) => html`<span class="senal en-contra" data-senal="${s.clave}">${icono('cerrar')}<span class="sr">En contra: </span>${s.texto}</span>`)}${!(p.a_favor || []).length && !(p.en_contra || []).length ? html`<span class="falta">Sin señales claras</span>` : ''}`;
  const nota = (p) => (p.nota ? html`<q class="nota-par">${p.nota}</q>` : '');
  if (g.pares.length === 1) return html`<div class="senales">${chips(g.pares[0])}${nota(g.pares[0])}</div>`;
  return html`<ul class="senales senales-pares">${g.pares.map((p) => html`<li><span class="par-letras" title="Fichas ${letras.get(p.a) ?? '?'} y ${letras.get(p.b) ?? '?'}">${letras.get(p.a) ?? '?'}–${letras.get(p.b) ?? '?'}</span>
    <span class="puntaje-par">${pctTexto(p.puntaje)}</span>${p.nivel && p.nivel !== g.nivel ? html`<span class="chip nivel" data-nivel="${p.nivel}">${NIVEL[p.nivel] || p.nivel}</span>` : ''}${chips(p)}${nota(p)}</li>`)}</ul>`;
}

/** Los botones del grupo y, si no se puede unir así, por qué. */
function accionesGrupo(g, e) {
  const motivo = bloqueoUnir(g, e);
  const sep = bloqueoSeparar(g);
  return html`${motivo ? html`<p class="bloqueo" id="bq-${g.clave}">${icono('alerta')}<span>${motivo}</span></p>` : ''}
    <div class="error-grupo" role="alert" hidden></div>
    <div class="botones-grupo"><button type="button" class="btn primario" data-unir aria-keyshortcuts="U" ${motivo ? html`disabled aria-describedby="bq-${g.clave}"` : ''}>${icono('hecho')} Es la misma persona</button>
      <button type="button" class="btn" data-separar aria-keyshortcuts="D" ${sep ? 'disabled' : ''}>Son distintas</button></div>`;
}

/** La tarjeta de un grupo: selección, nivel, puntaje, motivos, señales, avisos, la comparación y las acciones. */
function tarjetaGrupo(g, e) {
  const letras = letrasDe(g);
  const nombres = g.miembros.map((m) => m.nombre).join(' y ');
  return html`<article class="grupo-coinc${e.sel ? ' seleccionada' : ''}" data-clave="${g.clave}" data-nivel="${g.nivel}" tabindex="-1"
    aria-labelledby="gt-${g.clave}" aria-describedby="ayuda-atajos" aria-keyshortcuts="J K">
    <header class="grupo-cab">
      <label class="sel-grupo" title="Seleccionar (X)"><input type="checkbox" data-sel ${e.sel ? 'checked' : ''} aria-keyshortcuts="X"><span class="sr">Seleccionar este grupo</span></label>
      <h3 class="grupo-titulo" id="gt-${g.clave}"><span class="chip nivel" data-nivel="${g.nivel}">${NIVEL[g.nivel] || g.nivel}</span>
        <span class="puntaje-grupo${g.puntaje == null ? ' sin-puntaje' : ''}" title="${g.puntaje == null ? 'Sin puntaje: la propuso una persona del equipo o un alta simultánea' : 'Puntaje del cruce'}">${pctTexto(g.puntaje)}</span><span class="sr">: ${nombres}</span></h3>
      <span class="motivos-grupo">${(g.motivos || []).map((m) => html`<span class="chip borde">${MOTIVOS_COINCIDENCIA[m] || m.replace(/_/g, ' ')}</span>`)}</span>
      <span class="n-fichas">${plural(g.miembros.length, 'ficha', 'fichas')}${g.pares.length > 1 ? ` · ${plural(g.pares.length, 'par', 'pares')}` : ''}</span>
    </header>
    ${senalesGrupo(g, letras)}
    ${(g.avisos || []).length ? html`<ul class="avisos-grupo">${g.avisos.map((a) => html`<li>${icono('alerta')}<span>${a}</span></li>`)}</ul>` : ''}
    <div class="comparar-envoltura">${tablaComparar(g, e, letras)}</div>
    <div class="grupo-acciones">${accionesGrupo(g, e)}</div>
  </article>`;
}

export async function vistaCalidad(el, { q }) {
  let pestana = PESTANAS.some(([k]) => k === q.get('p')) ? q.get('p') : 'coincidencias';
  montar(el, html`
    <div class="cabecera"><div><h1>Calidad de datos</h1><div class="sub">Lo que la máquina no decide sola: usted confirma, y la base queda más completa.</div></div>
      <div class="acciones"><button class="btn" id="regeo">Recalcular ubicaciones</button></div></div>
    <div class="pestanas" role="tablist">
      ${PESTANAS.map(([k, t]) => html`<button role="tab" data-tab="${k}" aria-selected="${k === pestana}">${t}</button>`)}
    </div>
    <div id="cuerpo"></div>`);

  // Cada carga lleva un turno: si se cambió de pestaña mientras llegaba, no pinta encima de la nueva
  let turno = 0;
  const vigente = (t) => t === turno && el.isConnected;
  const VISTAS = { coincidencias, conflictos, solicitudes, situaciones, lugares, sin: sinReconocer };
  // Filtros de Coincidencias: viajan en la URL (el enlace «revisar» de la ficha trae `persona`). Ninguno es una clave
  // que el asistente lea de la dirección (agente.js, CLAVES_CONTEXTO): las coincidencias no le llegan
  const filtroC = {
    nivel: NIVELES.some(([k]) => k === q.get('nivel')) ? q.get('nivel') : '',
    motivo: /^[a-z_]{1,40}$/.test(q.get('motivo') || '') ? q.get('motivo') : '',
    persona: /^\d{1,12}$/.test(q.get('persona') || '') ? q.get('persona') : '',
    pagina: Math.max(1, Number.parseInt(q.get('pagina') || '1', 10) || 1),
  };
  let quitarTeclas = null; // los atajos de Coincidencias: se quitan al cambiar de pestaña o salir de la vista
  let detenerLote = null;  // «Unir las N muy probables» en curso

  async function pintar() {
    quitarTeclas?.();
    quitarTeclas = null;
    for (const b of el.querySelectorAll('[data-tab]')) b.setAttribute('aria-selected', b.dataset.tab === pestana);
    history.replaceState({}, '', url(`/calidad?p=${pestana}`));
    const c = $('#cuerpo', el);
    montar(c, html`<div class="cargando"><div class="giro"></div></div>`);
    c.onclick = null;
    c.onchange = null;
    const t = ++turno;
    try { await VISTAS[pestana](c, t); } catch (err) { if (vigente(t)) montar(c, html`<div class="aviso-legal">${err.message}</div>`); }
  }
  // Vuelve a cargar la pestaña después de una acción, solo si el usuario sigue en ella
  const recargar = (fn, nombre, c) => { if (pestana === nombre && el.isConnected) fn(c, ++turno); };

  const lado = (p, otro, rotulo) => {
    const tb = new Set((otro?.nombre || '').split(/\s+/));
    const marcado = html`${(p.nombre || '').split(/\s+/).map((w) => (tb.has(w) ? html`<span class="igual">${w}</span> ` : html`${w} `))}`;
    return html`<div class="lado"><span class="sec">${rotulo}</span><b><a href="/personas/${p.id}" data-ruta>${marcado}</a></b>${insigniasFuentes(p.fuentes)}
      <dl><dt>Cédula</dt><dd>${p.cedula || '—'}</dd><dt>Teléfono</dt><dd>${[p.telefono, p.telefono2].filter(Boolean).join(', ') || '—'}</dd>
      <dt>Lugar</dt><dd>${titulo(p.lugar || '') || '—'}</dd><dt>Dirección</dt><dd>${p.direccion || '—'}</dd>
      ${p.edad ? html`<dt>Edad</dt><dd>${p.edad} · ${p.sexo || ''}</dd>` : ''}${p.tramites ? html`<dt>Trámites</dt><dd>${p.tramites}</dd>` : ''}
      ${p.listas ? html`<dt>Listas</dt><dd>${p.listas}</dd>` : ''}${p.completitud != null ? html`<dt>Completitud</dt><dd>${p.completitud}%</dd>` : ''}</dl></div>`;
  };

  const etiquetaMotivo = (k, d) => `${MOTIVOS_COINCIDENCIA[k] || k.replace(/_/g, ' ')} (${num(d.motivos?.[k] || 0)})`;
  const textoCuenta = (d) => `${plural(d.total, 'grupo', 'grupos')} con ${plural(d.pares, 'coincidencia', 'coincidencias')} entre ${plural(d.personas, 'ficha', 'fichas')}.`;
  const textoUnirAlta = (n) => (n === 1 ? 'Unir la muy probable' : `Unir las ${num(n)} muy probables`);

  async function coincidencias(c, mio) {
    quitarTeclas?.();
    quitarTeclas = null;
    const f = filtroC;
    const enUrl = Object.entries({ p: 'coincidencias', nivel: f.nivel, motivo: f.motivo, persona: f.persona, pagina: f.pagina > 1 ? f.pagina : '' })
      .filter(([, v]) => v);
    history.replaceState({}, '', url('/calidad?') + new URLSearchParams(enUrl));
    const d = await api.get('/api/coincidencias/grupos', { nivel: f.nivel, motivo: f.motivo, persona: f.persona, pagina: f.pagina,
      por_pagina: POR_PAGINA_GRUPOS });
    if (!vigente(mio)) return;
    // Lo último de una página se resolvió: se muestra la última que queda (o la primera, si la cuenta no cuadra: así
    // no se vuelve a pedir la misma página vacía)
    const porPagina = d.por_pagina || POR_PAGINA_GRUPOS;
    if (!(d.grupos || []).length && f.pagina > 1 && d.total > 0) {
      const ultima = Math.max(1, Math.ceil(d.total / porPagina));
      f.pagina = ultima < f.pagina ? ultima : 1;
      return coincidencias(c, mio);
    }
    const grupos = d.grupos || [];
    const estados = new Map(grupos.map((g) => [g.clave, { conservar: g.destino ?? destinoPorDefecto(g.miembros), excluir: new Set(), sel: false }]));
    const est = (g) => estados.get(g.clave);
    const porClave = new Map(grupos.map((g) => [g.clave, g]));
    const resueltos = new Set();
    const totalNiveles = () => NIVELES.reduce((a, [k]) => a + (d.niveles?.[k] || 0), 0);
    if (!d.total && !totalNiveles() && !f.nivel && !f.motivo && !f.persona) {
      montar(c, html`<div class="tarjeta vacio"><b>Nada pendiente</b>Todas las coincidencias por nombre están resueltas.</div>`);
      return;
    }
    const claves = [...new Set([...Object.keys(MOTIVOS_COINCIDENCIA), ...Object.keys(d.motivos || {})])]
      .filter((k) => (d.motivos?.[k] || 0) > 0 || k === f.motivo);
    const paginas = Math.max(1, Math.ceil(d.total / porPagina));
    montar(c, html`<section class="unificacion" aria-label="Coincidencias por revisar">
      <div class="resumen-unif">
        <div class="niveles-unif" role="group" aria-label="Ver por nivel de confianza">
          <button type="button" class="chip nivel-filtro" data-nivel-filtro="" aria-pressed="${!f.nivel}">Todos <b data-cuenta-nivel="">${num(totalNiveles())}</b></button>
          ${NIVELES.map(([k, t]) => html`<button type="button" class="chip nivel-filtro" data-nivel-filtro="${k}" aria-pressed="${f.nivel === k}"><i class="punto-nivel" data-nivel="${k}" aria-hidden="true"></i>${t} <b data-cuenta-nivel="${k}">${num(d.niveles?.[k] || 0)}</b></button>`)}
        </div>
        <label class="campo motivo-unif"><span>Motivo</span><select data-motivo><option value="">Todos los motivos</option>
          ${claves.map((k) => html`<option value="${k}" ${k === f.motivo ? 'selected' : ''}>${etiquetaMotivo(k, d)}</option>`)}</select></label>
        <div class="unir-alta" ${d.niveles?.alta ? '' : 'hidden'}>
          <button type="button" class="btn primario grande" data-unir-alta>${icono('hecho')}<span data-texto-alta>${textoUnirAlta(d.niveles?.alta || 0)}</span></button>
          <small>Sin señales en contra y con evidencia fuerte: el mismo teléfono, correo, fecha de nacimiento o una cédula anterior.</small>
        </div>
      </div>
      ${leyendaFuentes(fuentesVisibles(true))}
      ${f.persona ? html`<div class="aviso-legal filtro-persona"><span>Solo el grupo de la <a href="/personas/${f.persona}" data-ruta>ficha ${f.persona}</a>.</span>
        <button type="button" class="btn chico" data-ver-todos>Ver todos los grupos</button></div>` : ''}
      <p class="cuenta-unif"><b id="cuenta-grupos">${textoCuenta(d)}</b> <span class="explica">Si son la misma persona, se unen: nada se pierde (lo distinto queda como dato alterno).</span></p>
      ${grupos.length ? html`
        <p class="ayuda-atajos" id="ayuda-atajos">Con el teclado: <kbd>J</kbd> y <kbd>K</kbd> pasan al grupo siguiente o al anterior, <kbd>X</kbd> lo selecciona, <kbd>U</kbd> lo une y <kbd>D</kbd> lo marca como personas distintas.</p>
        <p class="leyenda-comparar"><span class="igual-dato">Verde</span>: el mismo dato en dos o más fichas. <span class="choca">Rojo ondulado</span>: un dato que choca.</p>
        <div class="barra-seleccion" id="barra-sel">
          <span class="cuenta-sel" id="cuenta-sel" aria-live="polite"></span>
          <div class="botones-sel">
            <button type="button" class="btn primario chico" data-sel-unir hidden>${icono('hecho')} Unir</button>
            <button type="button" class="btn chico" data-sel-separar hidden>Marcar distintas</button>
            <button type="button" class="btn chico fantasma" data-sel-quitar hidden><span>Quitar<span class="mas-texto"> selección</span></span></button>
            <button type="button" class="btn chico" data-sel-todos><span>Seleccionar todos<span class="mas-texto"> los de esta página</span></span></button>
          </div>
        </div>
        <div class="lista-grupos">${grupos.map((g) => tarjetaGrupo(g, est(g)))}</div>
        ${paginas > 1 ? html`<div class="paginacion"><span>Página ${num(f.pagina)} de ${num(paginas)}</span>
          <span class="botones-pagina"><button type="button" class="btn chico" data-pagina="${f.pagina - 1}" ${f.pagina <= 1 ? 'disabled' : ''}>← Anterior</button>
          <button type="button" class="btn chico" data-pagina="${f.pagina + 1}" ${f.pagina >= paginas ? 'disabled' : ''}>Siguiente →</button></span></div>` : ''}`
      : html`<div class="tarjeta vacio"><b>${f.persona ? 'Esa ficha ya no tiene coincidencias pendientes' : 'Ningún grupo con estos filtros'}</b>${f.persona ? '' : 'Pruebe con otro nivel o motivo.'}
        <div class="volver-todos"><button type="button" class="btn" data-ver-todos>Ver todos los grupos</button></div></div>`}
    </section>`);

    const recargarC = () => {
      if (pestana !== 'coincidencias' || !el.isConnected) return;
      const t = ++turno;
      coincidencias(c, t).catch((err) => { if (vigente(t)) montar(c, html`<div class="aviso-legal">${err.message}</div>`); });
    };
    const tarjetaDe = (g) => c.querySelector(`.grupo-coinc[data-clave="${CSS.escape(g.clave)}"]`);
    const vivos = () => grupos.filter((g) => !resueltos.has(g.clave));
    let ocupado = false;
    let enLote = false;
    let claveActual = null;

    // ── Selección ──
    function pintarBarra() {
      const barra = $('#barra-sel', c);
      if (!barra) return;
      const v = vivos();
      const sel = v.filter((g) => est(g).sel);
      const fichas = sel.reduce((a, g) => a + g.miembros.length, 0);
      $('#cuenta-sel', barra).textContent = sel.length
        ? `${plural(sel.length, 'grupo seleccionado', 'grupos seleccionados')} · ${plural(fichas, 'ficha', 'fichas')}`
        : 'Seleccione grupos para resolverlos juntos';
      for (const b of $$('[data-sel-unir], [data-sel-separar], [data-sel-quitar]', barra)) { b.hidden = !sel.length; b.disabled = ocupado; }
      const todos = $('[data-sel-todos]', barra);
      todos.hidden = !v.length || sel.length === v.length;
      todos.disabled = ocupado;
      barra.classList.toggle('con-seleccion', sel.length > 0);
    }
    function seleccionar(g, si) {
      est(g).sel = si;
      const t = tarjetaDe(g);
      if (t) { t.classList.toggle('seleccionada', si); const x = $('[data-sel]', t); if (x) x.checked = si; }
    }

    // ── Conteos: se descuentan en el acto (el servidor los recalcula en la próxima carga) ──
    function pintarConteos() {
      for (const b of $$('[data-cuenta-nivel]', c)) b.textContent = num(b.dataset.cuentaNivel ? d.niveles?.[b.dataset.cuentaNivel] || 0 : totalNiveles());
      const alta = d.niveles?.alta || 0;
      const ua = $('.unir-alta', c);
      if (ua) { ua.hidden = !alta; $('[data-texto-alta]', ua).textContent = textoUnirAlta(alta); }
      const cu = $('#cuenta-grupos', c);
      if (cu) cu.textContent = textoCuenta(d);
      const sm = $('[data-motivo]', c);
      if (sm) for (const o of sm.options) if (o.value) o.textContent = etiquetaMotivo(o.value, d);
    }

    // ── Foco y recorrido con el teclado ──
    function enfocar(t, { desplazar = true } = {}) {
      if (!t) return;
      for (const x of $$('.grupo-coinc.actual', c)) x.classList.remove('actual');
      t.classList.add('actual');
      claveActual = t.dataset.clave;
      t.focus({ preventScroll: true });
      if (desplazar) t.scrollIntoView({ block: 'start', behavior: sinMovimiento() ? 'auto' : 'smooth' });
    }

    // La tarjeta resuelta se va (se desvanece y se pliega) y el foco pasa a la siguiente; sin tarjetas, se recarga
    function quitarGrupo(g) {
      resueltos.add(g.clave);
      est(g).sel = false;
      if (d.niveles && g.nivel in d.niveles) d.niveles[g.nivel] = Math.max(0, d.niveles[g.nivel] - 1);
      for (const m of g.motivos || []) if (d.motivos && m in d.motivos) d.motivos[m] = Math.max(0, d.motivos[m] - 1);
      d.total = Math.max(0, d.total - 1);
      d.pares = Math.max(0, d.pares - g.pares.length);
      d.personas = Math.max(0, d.personas - g.miembros.length);
      pintarConteos();
      const t = tarjetaDe(g);
      if (!t) return;
      const lista = $$('.grupo-coinc:not(.resuelta)', c);
      const i = lista.indexOf(t);
      const siguiente = lista[i + 1] || lista[i - 1] || null;
      const conFoco = t.contains(document.activeElement) || claveActual === g.clave;
      t.classList.add('resuelta');
      t.inert = true;
      if (conFoco && siguiente) enfocar(siguiente, { desplazar: false });
      const fin = () => {
        t.remove();
        if (!$('.grupo-coinc', c)) recargarC();
        else if (conFoco && siguiente?.isConnected) siguiente.scrollIntoView({ block: 'nearest' });
      };
      if (sinMovimiento()) { fin(); return; }
      setTimeout(() => {
        t.style.height = `${t.offsetHeight}px`;
        t.getBoundingClientRect(); // fija el alto actual para que el plegado tenga desde dónde ir
        t.classList.add('plegada');
        t.style.height = '0px';
        setTimeout(fin, 240);
      }, 220);
    }

    function mostrarError(t, x) {
      const caja = $('.error-grupo', t);
      if (!caja) return;
      t.classList.add('con-error');
      caja.hidden = false;
      montar(caja, html`${icono('alerta')}<span>${x?.error || 'No se pudo resolver este grupo.'}</span>${['cambio', 'parcial'].includes(x?.codigo)
        ? html`<button type="button" class="btn chico" data-recargar>Recargar</button>` : ''}`);
    }

    // ── Resolver: uno o varios grupos en una sola petición ──
    async function resolver(lista, decision) {
      if (ocupado || enLote || !lista.length) return;
      ocupado = true;
      const tanda = lista.slice(0, LOTE_GRUPOS); // una página trae 25: nunca llega al tope
      const tarjetas = tanda.map(tarjetaDe);
      for (const t of tarjetas) {
        if (!t) continue;
        t.classList.add('enviando');
        t.classList.remove('con-error');
        const caja = $('.error-grupo', t);
        if (caja) caja.hidden = true;
        for (const b of $$('[data-unir], [data-separar]', t)) b.disabled = true;
      }
      pintarBarra();
      let r;
      try {
        r = await api.post('/api/coincidencias/lote', { grupos: tanda.map((g) => cuerpoGrupo(g, est(g), decision)) }, { timeout: ESPERA_LOTE });
      } catch (err) {
        ocupado = false;
        tanda.forEach((g, i) => {
          const t = tarjetas[i];
          if (t?.isConnected) { t.classList.remove('enviando'); montar($('.grupo-acciones', t), accionesGrupo(g, est(g))); }
        });
        pintarBarra();
        avisoError(err);
        return;
      }
      ocupado = false;
      if (!vigente(mio)) { refrescarInsignias(); return; }
      const resultados = Array.isArray(r?.resultados) ? r.resultados : [];
      let bien = 0;
      tanda.forEach((g, i) => {
        const x = resultados[i];
        const t = tarjetas[i];
        if (x?.ok) { bien++; quitarGrupo(g); return; }
        if (t?.isConnected) {
          t.classList.remove('enviando');
          montar($('.grupo-acciones', t), accionesGrupo(g, est(g)));
          mostrarError(t, x);
        }
      });
      const mal = tanda.length - bien;
      const hecho = decision === 'unir'
        ? `${plural(r?.unidas ?? 0, 'ficha unida', 'fichas unidas')}${bien > 1 ? ` en ${num(bien)} grupos` : ''}`
        : `${plural(bien, 'grupo marcado', 'grupos marcados')} como personas distintas`;
      if (bien && mal) aviso(`${hecho}. ${plural(mal, 'grupo tuvo', 'grupos tuvieron')} un problema: vea su tarjeta.`, 'error', 6000);
      else if (bien) aviso(hecho);
      else aviso(mal === 1 ? 'No se pudo resolver el grupo: vea el aviso en su tarjeta.' : 'No se pudieron resolver: vea el aviso en cada tarjeta.', 'error', 6000);
      if (bien) refrescarInsignias();
      pintarBarra();
    }

    async function resolverSeleccion(decision) {
      const sel = vivos().filter((g) => est(g).sel);
      if (!sel.length || ocupado || enLote) return;
      if (decision === 'unir') {
        const validos = sel.filter((g) => !bloqueoUnir(g, est(g)));
        const saltan = sel.length - validos.length;
        if (!validos.length) {
          aviso(saltan === 1 ? 'Ese grupo no se puede unir así: vea el aviso en su tarjeta.' : 'Ninguno de esos grupos se puede unir así: vea el aviso en cada tarjeta.', 'error', 6000);
          return;
        }
        const fichas = validos.reduce((a, g) => a + incluidas(g, est(g)).length, 0);
        const dudosas = validos.filter((g) => g.nivel === 'baja').length;
        const partes = [`¿Unir ${plural(validos.length, 'grupo', 'grupos')}? Sus ${num(fichas)} fichas quedarán en ${num(validos.length)}; lo distinto pasa a datos alternos.`];
        if (dudosas) partes.push(dudosas === 1 ? 'Uno es dudoso: tiene señales en contra.' : `${num(dudosas)} son dudosos: tienen señales en contra.`);
        if (saltan) partes.push(saltan === 1 ? 'Uno de los seleccionados no se puede unir así y queda sin tocar.' : `${num(saltan)} de los seleccionados no se pueden unir así y quedan sin tocar.`);
        if (!await confirmar(partes.join(' '), { si: validos.length === 1 ? 'Unir' : `Unir ${num(validos.length)} grupos` })) return;
        await resolver(validos, 'unir');
      } else {
        const validos = sel.filter((g) => !bloqueoSeparar(g));
        if (!validos.length) { aviso('Esos grupos son demasiado grandes para resolverlos de una vez.', 'error', 6000); return; }
        if (!await confirmar(`¿Marcar ${plural(validos.length, 'grupo', 'grupos')} como personas distintas? Sus coincidencias no se volverán a proponer.`,
          { si: 'Marcar distintas' })) return;
        await resolver(validos, 'separar');
      }
    }

    // ── «Unir las N muy probables»: pide de a 50, las une con la ficha por defecto y sigue hasta que no queden ──
    async function unirMuyProbables() {
      if (ocupado || enLote) return;
      let info;
      try { info = await api.get('/api/coincidencias/grupos', { nivel: 'alta', motivo: f.motivo, por_pagina: 1 }); } catch (err) { avisoError(err); return; }
      if (!vigente(mio)) return;
      const n = info.total || 0;
      if (!n) { aviso('Ya no quedan grupos muy probables'); recargarC(); return; }
      const texto = n === 1
        ? `Se unirán las ${num(info.personas)} fichas del grupo muy probable en una sola.`
        : `Se unirán las fichas de ${num(n)} grupos muy probables: ${num(info.personas)} fichas quedarán en ${num(n)}.`;
      if (!await confirmar(`${texto} En cada grupo se conserva la ficha con cédula (o la más completa) y lo distinto queda como dato alterno. Cada unión queda en la auditoría.`,
        { si: n === 1 ? 'Unir' : `Unir ${num(n)} grupos` })) return;
      if (!vigente(mio)) return;
      enLote = true;
      let detenido = false;
      const { el: dlg, cerrar, listo } = dialogo({ titulo: 'Uniendo las muy probables',
        cuerpo: html`<div class="progreso-lote">
          <p class="estado-lote" data-estado aria-live="polite">Buscando los grupos…</p>
          <div class="barra-progreso" role="progressbar" aria-label="Avance" aria-valuemin="0" aria-valuemax="${n}" aria-valuenow="0"><i></i></div>
          <dl class="cifras-lote"><div><dt>Grupos unidos</dt><dd data-grupos>0</dd></div><div><dt>Fichas unidas</dt><dd data-unidas>0</dd></div>
            <div><dt>Con error</dt><dd data-errores>0</dd></div></dl>
          <ul class="errores-lote" data-lista-errores hidden></ul></div>`,
        pie: html`<button type="button" class="btn" data-detener>Detener</button>` });
      // Cerrar el diálogo (✕, Escape o el fondo) también detiene: la tanda en curso termina y no se pide otra
      listo.then(() => { detenido = true; });
      detenerLote = () => { detenido = true; cerrar(null); };
      $('[data-detener]', dlg).onclick = (e) => {
        detenido = true;
        e.currentTarget.disabled = true;
        e.currentTarget.textContent = 'Deteniendo…';
        $('[data-estado]', dlg).textContent = 'Se detiene al terminar la tanda en curso…';
      };
      const fallidas = new Set(); // claves que fallaron: no se vuelven a intentar
      const cuenta = { grupos: 0, unidas: 0, errores: 0, hechos: 0 };
      const errores = [];
      let problema = null;
      const pintarAvance = (estado) => {
        if (!dlg.isConnected) return;
        if (estado) $('[data-estado]', dlg).textContent = estado;
        const barra = $('.barra-progreso', dlg);
        barra.setAttribute('aria-valuenow', String(Math.min(n, cuenta.hechos)));
        $('i', barra).style.width = `${Math.min(100, Math.round((cuenta.hechos / n) * 100))}%`;
        $('[data-grupos]', dlg).textContent = num(cuenta.grupos);
        $('[data-unidas]', dlg).textContent = num(cuenta.unidas);
        $('[data-errores]', dlg).textContent = num(cuenta.errores);
        const ul = $('[data-lista-errores]', dlg);
        ul.hidden = !errores.length;
        montar(ul, html`${errores.slice(0, 20).map((x) => html`<li><b>${x.nombres}</b>: ${x.error}</li>`)}${errores.length > 20 ? html`<li>Y ${plural(errores.length - 20, 'grupo', 'grupos')} más.</li>` : ''}`);
      };
      try {
        let pagina = 1;
        // Tope de vueltas: cada una une o descarta al menos un grupo, o avanza de página
        for (let vuelta = 0; vuelta < Math.ceil(n / LOTE_GRUPOS) * 4 + 20 && !detenido; vuelta++) {
          const r = await api.get('/api/coincidencias/grupos', { nivel: 'alta', motivo: f.motivo, pagina, por_pagina: LOTE_GRUPOS });
          const todos = (r.grupos || []).filter((g) => g.nivel === 'alta' && !fallidas.has(g.clave));
          for (const g of todos.filter((x) => x.pares.length > MAX_PARES_GRUPO)) {
            fallidas.add(g.clave);
            cuenta.errores++; cuenta.hechos++;
            errores.push({ nombres: g.miembros.map((m) => m.nombre).join(' y '), error: bloqueoSeparar(g) });
          }
          const tanda = todos.filter((g) => g.pares.length <= MAX_PARES_GRUPO);
          if (!tanda.length) {
            // Lo que queda en esta página ya falló una vez: se sigue con la siguiente, si hay
            if (pagina * LOTE_GRUPOS < (r.total || 0)) { pagina++; continue; }
            break;
          }
          if (detenido) break;
          pintarAvance(`Uniendo ${plural(tanda.length, 'grupo', 'grupos')}…`);
          const res = await api.post('/api/coincidencias/lote', { grupos: tanda.map((g) => ({ pares: g.pares.map((p) => p.id), decision: 'unir' })) },
            { timeout: ESPERA_LOTE });
          const rs = Array.isArray(res?.resultados) ? res.resultados : [];
          tanda.forEach((g, i) => {
            cuenta.hechos++;
            if (rs[i]?.ok) { cuenta.grupos++; return; }
            fallidas.add(g.clave);
            cuenta.errores++;
            errores.push({ nombres: g.miembros.map((m) => m.nombre).join(' y '), error: rs[i]?.error || 'No se pudo unir.' });
          });
          cuenta.unidas += Number(res?.unidas) || 0;
          pintarAvance();
        }
      } catch (err) {
        problema = err;
      } finally {
        enLote = false;
        detenerLote = null;
      }
      const resumen = `${detenido ? 'Detenido' : 'Listo'}: ${plural(cuenta.unidas, 'ficha unida', 'fichas unidas')} en ${plural(cuenta.grupos, 'grupo', 'grupos')}${cuenta.errores ? `; ${plural(cuenta.errores, 'grupo quedó', 'grupos quedaron')} para revisar a mano` : ''}.`;
      if (dlg.isConnected) {
        pintarAvance(problema ? `${problema.message} ${resumen}` : resumen);
        $('.cab h2', dlg).textContent = problema ? 'La unión se interrumpió' : detenido ? 'Unión detenida' : 'Unión terminada';
        montar($('.pie', dlg), html`<button type="button" class="btn oscuro" data-cerrar>Cerrar</button>`);
        $('[data-cerrar]', $('.pie', dlg))?.focus();
      } else if (problema) avisoError(problema);
      else aviso(resumen);
      if (cuenta.grupos) refrescarInsignias();
      if (vigente(mio)) recargarC();
    }

    // ── Eventos ──
    pintarBarra();
    c.onclick = (e) => {
      const t = e.target;
      const nf = t.closest('[data-nivel-filtro]');
      if (nf) { f.nivel = nf.dataset.nivelFiltro; f.pagina = 1; recargarC(); return; }
      if (t.closest('[data-ver-todos]')) { Object.assign(f, { nivel: '', motivo: '', persona: '', pagina: 1 }); recargarC(); return; }
      if (t.closest('[data-unir-alta]')) { unirMuyProbables(); return; }
      const pg = t.closest('[data-pagina]');
      if (pg) { if (!pg.disabled) { f.pagina = Number(pg.dataset.pagina); recargarC(); el.scrollIntoView(); } return; }
      if (t.closest('[data-sel-todos]')) { for (const g of vivos()) seleccionar(g, true); pintarBarra(); $('[data-sel-unir]', c)?.focus(); return; }
      if (t.closest('[data-sel-quitar]')) { for (const g of vivos()) seleccionar(g, false); pintarBarra(); $('[data-sel-todos]', c)?.focus(); return; }
      if (t.closest('[data-sel-unir]')) { resolverSeleccion('unir'); return; }
      if (t.closest('[data-sel-separar]')) { resolverSeleccion('separar'); return; }
      if (t.closest('[data-recargar]')) { recargarC(); return; }
      const tarjeta = t.closest('.grupo-coinc');
      const g = tarjeta && porClave.get(tarjeta.dataset.clave);
      if (!g || resueltos.has(g.clave)) return;
      if (claveActual !== g.clave) {
        for (const x of $$('.grupo-coinc.actual', c)) x.classList.remove('actual');
        tarjeta.classList.add('actual');
        claveActual = g.clave;
      }
      if (t.closest('[data-unir]')) { resolver([g], 'unir'); return; }
      if (t.closest('[data-separar]')) resolver([g], 'separar');
    };
    c.onchange = (e) => {
      const t = e.target;
      if (t.matches('[data-motivo]')) { f.motivo = t.value; f.pagina = 1; recargarC(); return; }
      const tarjeta = t.closest('.grupo-coinc');
      const g = tarjeta && porClave.get(tarjeta.dataset.clave);
      if (!g) return;
      const s = est(g);
      if (t.matches('[data-sel]')) { seleccionar(g, t.checked); pintarBarra(); return; }
      if (t.matches('[data-conservar]')) s.conservar = Number(t.value);
      else if (t.matches('[data-excluir]')) {
        const id = Number(t.value);
        if (t.checked) s.excluir.add(id); else s.excluir.delete(id);
        // La conservada no puede quedar fuera: pasa a la que el servidor elegiría entre las que quedan
        if (s.excluir.has(s.conservar)) s.conservar = destinoPorDefecto(incluidas(g, s)) ?? s.conservar;
      } else return;
      // Se repinta la comparación y los botones del grupo; el foco vuelve al control que se tocó
      const envoltura = $('.comparar-envoltura', tarjeta);
      const x = envoltura.scrollLeft;
      const selector = `[${t.matches('[data-conservar]') ? 'data-conservar' : 'data-excluir'}][value="${t.value}"]`;
      montar(envoltura, tablaComparar(g, s, letrasDe(g)));
      envoltura.scrollLeft = x;
      montar($('.grupo-acciones', tarjeta), accionesGrupo(g, s));
      $(selector, tarjeta)?.focus();
    };
    // Atajos (escritorio): no con el foco en un campo de texto ni con un diálogo abierto o el asistente
    const teclas = (e) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
      const k = e.key.toLowerCase();
      if (!'jkxud'.includes(k) || !c.isConnected || pestana !== 'coincidencias') return;
      if (document.querySelector('dialog[open]')) return;
      const a = e.target instanceof Element ? e.target : null;
      if (a?.closest('textarea, select, [contenteditable]:not([contenteditable="false"]), #agente-panel')) return;
      if (a?.matches('input') && !['checkbox', 'radio', 'button', 'submit', 'reset'].includes(a.type)) return;
      const lista = $$('.grupo-coinc:not(.resuelta)', c);
      if (!lista.length) return;
      const actual = lista.find((x) => x.contains(document.activeElement)) || lista.find((x) => x.dataset.clave === claveActual) || null;
      e.preventDefault();
      if (k === 'j' || k === 'k') {
        const i = actual ? lista.indexOf(actual) : -1;
        enfocar(k === 'j' ? lista[Math.min(lista.length - 1, i + 1)] : lista[Math.max(0, i - 1)]);
        return;
      }
      if (!actual) { aviso('Elija un grupo con J o K', 'ok', 2500); return; }
      const g = porClave.get(actual.dataset.clave);
      if (k === 'x') { seleccionar(g, !est(g).sel); pintarBarra(); return; }
      const b = $(k === 'u' ? '[data-unir]' : '[data-separar]', actual);
      if (b && !b.disabled) { resolver([g], k === 'u' ? 'unir' : 'separar'); return; }
      if (!ocupado) aviso(k === 'u' ? bloqueoUnir(g, est(g)) || 'Este grupo no se puede unir así.' : bloqueoSeparar(g) || 'Espere a que termine lo anterior.', 'error', 5000);
    };
    document.addEventListener('keydown', teclas);
    quitarTeclas = () => document.removeEventListener('keydown', teclas);
  }

  async function conflictos(c, mio) {
    const lista = await api.get('/api/conflictos');
    if (!vigente(mio)) return;
    if (!lista.length) { montar(c, html`<div class="tarjeta vacio"><b>Sin conflictos de cédula</b>Ninguna fila trae una cédula que choque con la base.</div>`); return; }
    const fila = (r, x) => html`<div class="lado"><span class="sec">Fila · ${insigniaFuente(x.fuente, { conNombre: true })}${r.fila ? ` · fila ${r.fila}` : ''}</span><b>${r.nombre || '—'}</b>
      <dl><dt>Cédula</dt><dd>${r.cedula || '—'}${r.cedula && r.tipo_documento ? ` (${r.tipo_documento})` : ''}</dd>
      ${x.cedula && x.cedula !== r.cedula ? html`<dt>En conflicto</dt><dd>${x.cedula}</dd>` : ''}
      ${r.cedula_digitada || r.cedula_repetida ? html`<dt>Escrita</dt><dd>${r.cedula_digitada || '—'} · repetida ${r.cedula_repetida || '—'}</dd>` : ''}
      <dt>Teléfonos</dt><dd>${(r.telefonos || []).join(', ') || '—'}</dd><dt>Dirección</dt><dd>${r.direccion || '—'}</dd>
      ${r.edad || r.fecha_nacimiento ? html`<dt>Edad</dt><dd>${r.fecha_nacimiento || r.edad} · ${r.sexo || ''}</dd>` : ''}</dl></div>`;
    const botones = (x) => {
      const aplicar = html`<button class="btn chico primario" data-r="aplicar">Aplicar</button>`;
      const descartar = html`<button class="btn chico" data-r="descartar">Descartar</button>`;
      if (x.motivo === 'posible_digitacion') return html`<button class="btn chico primario" data-r="corregir">Corregir cédula</button>${descartar}`;
      if (x.motivo === 'dictada' && x.duena) return html`<button class="btn chico primario" data-r="reportar">Reportar duplicado</button>${descartar}`;
      return html`${aplicar}${descartar}`;
    };
    const ayuda = {
      nombre_distinto: 'La cédula ya está en una ficha con otro nombre. «Aplicar» toma la fila como de esta persona (sin cambiar su cédula); si es otra persona, descártela.',
      cedula_anterior: 'La fila trae una cédula que esta ficha tuvo antes. «Aplicar» completa la ficha con la fila.',
      posible_digitacion: 'La cédula difiere en un dígito de otra, o la planilla trae dos cédulas distintas. Nunca se une: corrija la cédula con su motivo o descarte el aviso.',
      dictada: 'Cédula que el titular le dictó al consultor. «Aplicar» la asigna si sigue libre; si ya es de otra ficha, repórtelas como duplicado.',
    };
    montar(c, html`<p class="sec">${num(lista.length)} conflictos. Ninguno mezcla datos hasta que usted decida.</p>
      <div style="display:flex;flex-direction:column;gap:12px">${lista.map((x) => html`<div class="tarjeta" data-k="${x.id}">
        <header style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px"><span class="chip ambar">${MOTIVOS_CONFLICTO[x.motivo] || x.motivo}</span>
          ${x.puntaje_nombre != null ? html`<span class="sec">Parecido del nombre: ${Math.round(x.puntaje_nombre * 100)}%</span>` : ''}
          <span class="sec">${fecha(x.creado_en, true)}</span></header>
        <p class="sec" style="margin-top:0">${ayuda[x.motivo] || ''}</p>
        <div class="par">${fila(x.registro || {}, x)}
          <div class="medio">${botones(x)}</div>
          ${x.persona ? lado(x.persona, x.registro, 'Ficha') : html`<div class="lado"><span class="sec">Ficha</span><b>Ya no está activa</b></div>`}</div>
        ${x.duena ? html`<div class="par" style="margin-top:10px"><div></div><div class="medio"><span class="sec">Dueña de la cédula</span></div>${lado(x.duena, x.persona, 'Ficha con esa cédula')}</div>` : ''}
        ${x.otra_persona ? html`<div class="par" style="margin-top:10px"><div></div><div class="medio"><span class="sec">Cédula parecida</span></div>${lado(x.otra_persona, x.persona, 'Otra ficha')}</div>` : ''}
      </div>`)}</div>`);
    c.onclick = async (e) => {
      const b = e.target.closest('[data-r]');
      if (!b) return;
      const tarjeta = b.closest('[data-k]');
      const id = tarjeta.dataset.k;
      const resolver = async (cuerpo) => {
        await api.post(`/api/conflictos/${id}`, cuerpo);
        aviso('Conflicto resuelto');
        recargar(conflictos, 'conflictos', c);
      };
      if (b.dataset.r === 'corregir') { corregirCedula(lista.find((x) => String(x.id) === id), resolver); return; }
      if (b.dataset.r === 'aplicar' && !await confirmar('¿La fila es de esta persona? Se completará la ficha y lo distinto quedará como dato alterno.', { si: 'Aplicar' })) return;
      b.disabled = true;
      try { await resolver({ decision: b.dataset.r }); } catch (err) { avisoError(err); b.disabled = false; }
    };
  }

  function corregirCedula(x, resolver) {
    const sugerida = x.registro?.cedula_repetida || x.cedula || '';
    const { el: d, cerrar } = dialogo({ titulo: 'Corregir cédula',
      cuerpo: html`<form class="form" id="f-ced">
        <p class="sec ancho" style="margin:0">Escriba la cédula correcta. La cédula actual de la ficha (si tiene) pasa a sus cédulas anteriores.</p>
        <label class="campo"><span>Cédula correcta</span><input name="cedula" inputmode="numeric" autocomplete="off" required pattern="[0-9]{5,11}" value="${sugerida}"></label>
        <label class="campo ancho"><span>Motivo</span><input name="motivo" maxlength="300" value="Corrección de un posible error de digitación"></label></form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Corregir</button>` });
    $('#g', d).onclick = async () => {
      const f = $('#f-ced', d);
      if (!f.reportValidity()) return;
      const datos = datosForm(f);
      try { await resolver({ decision: 'corregir', cedula_correcta: datos.cedula, motivo: datos.motivo }); cerrar(); } catch (err) { avisoError(err); }
    };
  }

  async function solicitudes(c, mio) {
    const lista = await api.get('/api/solicitudes');
    if (!vigente(mio)) return;
    const plazo = (s) => {
      if (s.dias_restantes == null) return html`<span class="sec">Sin plazo legal</span>`;
      if (s.vencida) return html`<span class="chip rojo">Vencida (${fecha(s.vence)})</span>`;
      return html`<span class="chip ${s.dias_restantes <= 3 ? 'ambar' : 'verde'}">${num(s.dias_restantes)} días · ${fecha(s.vence)}</span>`;
    };
    const tabla = (filas, vacio) => (filas.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Tipo</th><th>Persona</th><th>Descripción</th><th>Registró</th><th>Plazo</th><th>Estado</th><th></th></tr></thead>
      <tbody>${filas.map((s) => html`<tr style="cursor:default" data-s="${s.id}"><td><b>${TIPOS_SOLICITUD[s.tipo] || s.tipo}</b><div class="sec">${s.canal || ''}</div></td>
        <td>${s.persona_id ? html`<a href="/personas/${s.persona_id}" data-ruta>${s.persona || `Persona ${s.persona_id}`}</a>` : '—'}</td>
        <td style="max-width:340px;white-space:pre-wrap">${s.descripcion || ''}</td><td class="sec">${s.creado_por?.usuario || ''}<br>${fecha(s.ts, true)}</td>
        <td>${plazo(s)}</td><td>${ESTADOS_SOLICITUD[s.estado] || s.estado}</td>
        <td><button class="btn chico" data-responder="${s.id}">Responder</button></td></tr>`)}</tbody></table></div>` : html`<p class="sec">${vacio}</p>`);
    const titulares = lista.filter((s) => s.tipo !== 'registro');
    const registros = lista.filter((s) => s.tipo === 'registro');
    montar(c, html`<p class="sec">Consultas (10 días hábiles) y reclamos de corrección, supresión o revocatoria (15 días hábiles) de los titulares (Ley 1581, arts. 14 y 15). Mientras un reclamo está abierto, la persona sale de las colas.</p>
      ${tabla(titulares, 'No hay solicitudes abiertas de titulares.')}
      <h2 style="margin-top:22px">Pedidos de registro de consultores</h2>
      <p class="sec">Personas que llamaron y no están en la base: créelas usted desde Habitantes.</p>
      ${tabla(registros, 'No hay pedidos de registro abiertos.')}`);
    c.onclick = (e) => {
      const b = e.target.closest('[data-responder]');
      if (!b) return;
      const s = lista.find((x) => String(x.id) === b.dataset.responder);
      const { el: d, cerrar } = dialogo({ titulo: `${TIPOS_SOLICITUD[s.tipo] || s.tipo}${s.persona ? ` · ${s.persona}` : ''}`,
        cuerpo: html`<form class="form" id="f-sol"><p class="ancho" style="margin:0;white-space:pre-wrap">${s.descripcion || ''}</p>
          <label class="campo"><span>Estado</span><select name="estado">${Object.entries(ESTADOS_SOLICITUD).map(([k, t]) => html`<option value="${k}" ${k === s.estado ? 'selected' : ''}>${t}</option>`)}</select></label>
          <label class="campo ancho"><span>Respuesta al titular</span><textarea name="respuesta" maxlength="2000">${s.respuesta || ''}</textarea></label></form>`,
        pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Guardar</button>` });
      $('#g', d).onclick = async () => {
        try {
          await api.patch(`/api/solicitudes/${s.id}`, datosForm($('#f-sol', d)));
          cerrar(); aviso('Solicitud actualizada'); recargar(solicitudes, 'solicitudes', c);
        } catch (err) { avisoError(err); }
      };
    };
  }

  async function situaciones(c, mio) {
    const lista = await api.get('/api/situaciones');
    if (!vigente(mio)) return;
    if (!lista.length) { montar(c, html`<div class="tarjeta vacio"><b>Nada por confirmar</b>No hay personas reportadas como fallecidas o fuera de Yondó.</div>`); return; }
    montar(c, html`<p class="sec">Mientras no se revierta, la persona queda fuera de colas, listas de trabajo e indicadores. Nada se borra; si corresponde, suprímala desde su ficha.</p>
      <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Persona</th><th>Situación</th><th>Lugar</th><th>Reportado</th><th></th></tr></thead>
      <tbody>${lista.map((p) => html`<tr style="cursor:default" data-p="${p.id}"><td><a href="/personas/${p.id}" data-ruta><b>${p.nombre}</b></a></td>
        <td><span class="chip ambar">${SITUACIONES[p.situacion?.estado] || p.situacion?.estado}</span></td><td>${titulo(p.lugar || '') || '—'}</td>
        <td class="sec">${fecha(p.situacion?.ts, true)}${p.situacion?.fuente ? ` · ${p.situacion.fuente}` : ''}</td>
        <td style="white-space:nowrap"><button class="btn chico primario" data-s="confirmar">Confirmar</button> <button class="btn chico" data-s="revertir">Revertir</button></td></tr>`)}</tbody></table></div>`);
    c.onclick = async (e) => {
      const b = e.target.closest('[data-s]');
      if (!b) return;
      b.disabled = true;
      try {
        await api.post(`/api/situaciones/${b.closest('[data-p]').dataset.p}`, { decision: b.dataset.s });
        aviso(b.dataset.s === 'confirmar' ? 'Situación confirmada' : 'La persona vuelve a estar activa');
        recargar(situaciones, 'situaciones', c);
      } catch (err) { avisoError(err); b.disabled = false; }
    };
  }

  async function lugares(c, mio) {
    const ls = await api.get('/api/lugares');
    if (!vigente(mio)) return;
    const sinPunto = ls.filter((l) => l.lat == null && l.n > 0);
    montar(c, html`
      ${sinPunto.length ? html`<div class="aviso-legal" style="margin-bottom:14px"><b>${num(sinPunto.length)} lugares con habitantes no tienen punto.</b> Ubíquelos en el mapa y todas sus personas quedarán georreferenciadas.</div>` : ''}
      <div style="display:flex;justify-content:flex-end;margin-bottom:10px"><button class="btn primario chico" id="nuevo-lugar">Nuevo lugar</button></div>
      <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Lugar</th><th>Tipo</th><th>Zona</th><th class="num">Personas</th><th>Punto</th><th>Fuente</th><th></th></tr></thead>
      <tbody>${ls.map((l) => html`<tr style="cursor:default" data-l="${l.id}">
        <td><b>${titulo(l.nombre)}</b>${l.alias.length ? html`<div class="sec">También: ${l.alias.map(titulo).join(', ')}</div>` : ''}</td>
        <td>${l.tipo.replace('_', ' ')}</td><td>${l.zona}</td><td class="num">${num(l.n)}</td>
        <td>${l.lat != null ? html`<span class="chip verde">${l.tiene_poligono ? 'Polígono' : 'Punto'}</span>` : html`<span class="chip ambar">Falta</span>`}</td>
        <td class="sec">${l.fuente || ''}${l.precision ? ' · ' + l.precision : ''}</td>
        <td style="white-space:nowrap"><button class="btn chico" data-ubicar="${l.id}">Ubicar</button> <button class="btn chico fantasma" data-alias="${l.id}">Alias</button></td></tr>`)}</tbody></table></div>`);
    c.onclick = async (e) => {
      const u = e.target.closest('[data-ubicar]');
      if (u) {
        const l = ls.find((x) => x.id === Number(u.dataset.ubicar));
        const p = await elegirPunto({ titulo: `Ubicar ${titulo(l.nombre)}`, inicial: l.lat != null ? [l.lon, l.lat] : null,
          ayuda: 'Marque el centro del barrio o el caserío de la vereda. Las personas de este lugar sin dirección exacta tomarán este punto.' });
        if (!p) return;
        try {
          await api.patch(`/api/lugares/${l.id}`, { lon: p[0], lat: p[1] });
          aviso('Lugar ubicado y personas recalculadas'); recargar(lugares, 'lugares', c);
        } catch (err) { avisoError(err); }
        return;
      }
      const a = e.target.closest('[data-alias]');
      if (a) {
        const l = ls.find((x) => x.id === Number(a.dataset.alias));
        const { el: d, cerrar } = dialogo({ titulo: `Otros nombres de ${titulo(l.nombre)}`,
          cuerpo: html`<p class="sec" style="margin-top:0">Uno por línea: cómo lo escribe la gente en las direcciones.</p><textarea class="entrada" id="alias" style="min-height:140px">${l.alias.join('\n')}</textarea>`,
          pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Guardar</button>` });
        $('#g', d).onclick = async () => {
          try {
            await api.patch(`/api/lugares/${l.id}`, { alias: $('#alias', d).value.split('\n').map((s) => s.trim()).filter(Boolean) });
            cerrar(); aviso('Alias guardados; ubicaciones recalculadas'); recargar(lugares, 'lugares', c);
          } catch (err) { avisoError(err); }
        };
        return;
      }
      if (e.target.closest('#nuevo-lugar')) nuevoLugar('', () => recargar(lugares, 'lugares', c));
    };
  }

  async function sinReconocer(c, mio) {
    const [ls, todos] = await Promise.all([api.get('/api/lugares/sin-reconocer'), api.get('/api/lugares')]);
    if (!vigente(mio)) return;
    montar(c, html`<p class="sec">Nombres escritos en las direcciones que no coinciden con ningún barrio o vereda. Créelos como lugar nuevo o agréguelos como otro nombre de uno existente.</p>
      ${ls.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Como lo escribieron</th><th class="num">Personas</th><th>Agregar como alias de…</th><th></th></tr></thead>
      <tbody>${ls.map((x) => html`<tr style="cursor:default" data-t="${x.texto}"><td><b>${x.texto}</b></td><td class="num">${num(x.n)}</td>
        <td><select class="entrada" data-destino><option value="">Elegir lugar…</option>${todos.map((l) => html`<option value="${l.id}">${titulo(l.nombre)} · ${l.tipo}</option>`)}</select></td>
        <td style="white-space:nowrap"><button class="btn chico" data-como-alias>Agregar</button> <button class="btn chico fantasma" data-crear>Crear lugar</button></td></tr>`)}</tbody></table></div>`
        : html`<div class="tarjeta vacio"><b>Todo reconocido</b></div>`}`);
    c.onclick = async (e) => {
      const tr = e.target.closest('tr[data-t]');
      if (!tr) return;
      const texto = tr.dataset.t;
      if (e.target.closest('[data-como-alias]')) {
        const dest = Number(tr.querySelector('[data-destino]').value);
        if (!dest) { aviso('Elija el lugar', 'error'); return; }
        const l = todos.find((x) => x.id === dest);
        try {
          await api.patch(`/api/lugares/${dest}`, { alias: [...l.alias, texto] });
          aviso(`«${texto}» ahora se reconoce como ${titulo(l.nombre)}`);
          recargar(sinReconocer, 'sin', c);
        } catch (err) { avisoError(err); }
      } else if (e.target.closest('[data-crear]')) nuevoLugar(texto, () => recargar(sinReconocer, 'sin', c));
    };
  }

  function nuevoLugar(nombre, despues) {
    let punto = null;
    const { el: d, cerrar } = dialogo({ titulo: 'Nuevo lugar',
      cuerpo: html`<form class="form" id="f-lugar">
        <label class="campo ancho"><span>Nombre</span><input name="nombre" value="${nombre}" required></label>
        <label class="campo"><span>Tipo</span><select name="tipo"><option value="barrio">Barrio</option><option value="sector">Sector</option><option value="vereda">Vereda</option>
          <option value="caserio">Caserío</option><option value="centro_poblado">Centro poblado</option><option value="corregimiento">Corregimiento</option></select></label>
        <label class="campo"><span>Zona</span><select name="zona"><option value="urbana">Urbana</option><option value="rural">Rural</option></select></label>
        <div class="ancho"><button type="button" class="btn chico" id="p">Marcar en el mapa</button> <span class="sec" id="pt"></span></div></form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Crear</button>` });
    $('#p', d).onclick = async () => { punto = await elegirPunto({ titulo: 'Punto del lugar' }); if (punto) $('#pt', d).textContent = `${punto[1].toFixed(5)}, ${punto[0].toFixed(5)}`; };
    $('#g', d).onclick = async () => {
      const f = $('#f-lugar', d);
      if (!f.reportValidity()) return;
      const datos = datosForm(f);
      if (punto) { datos.lon = punto[0]; datos.lat = punto[1]; }
      try { await api.post('/api/lugares', datos); cerrar(); aviso('Lugar creado; personas recalculadas'); despues(); } catch (err) { aviso(err.message, 'error'); }
    };
  }

  el.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-tab]');
    if (t) { pestana = t.dataset.tab; pintar(); }
    const regeo = e.target.closest('#regeo');
    if (regeo && !regeo.disabled) {
      regeo.disabled = true;
      try {
        const r = await api.post('/api/georreferenciar');
        aviso(`Ubicaciones recalculadas: ${num(Object.entries(r.por_precision).filter(([k]) => k !== 'sin_ubicar').reduce((a, [, v]) => a + v, 0))} ubicadas`);
      } catch (err) { avisoError(err); } finally { regeo.disabled = false; }
    }
  });
  pintar();
  // Al salir de la vista: fuera los atajos de teclado y se detiene «Unir las N muy probables» (su diálogo vive en <body>)
  return () => { quitarTeclas?.(); detenerLote?.(); };
}
