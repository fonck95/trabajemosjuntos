// Habitantes (7.3): búsqueda, filtros combinables (plegados en el celular), filas o tarjetas con la proyección del
// rol, «Completar» con «Guardar y siguiente», paginación con el tope del planillero y exportación. Las columnas y los
// primeros filtros son los datos principales de la ficha (los 17: nombre, cédula, sexo y edad, teléfono y correo,
// dirección, barrio y zona, tipo y «Liderado por», perfil profesional, ocupación, estado civil y jefe de hogar); el
// puesto y la mesa, el abordaje y lo demás van en «Más filtros». A y K filtran además por tipo de persona, por quién la
// lidera (o sin líder) y por reunión (las intervenidas en ella), y abren la lista de líderes y concejales.
import { api, descargar, puede, sesion } from '../api.js';
import { url } from '../base.js';
import {
  ESTADOS_ABORDAJE, ESTADOS_CIVILES, ETIQUETAS_CAMPOS, RANGOS_EDAD, SEXOS, SITUACIONES, TIPOS_PERSONA, enmascarar, rangoAParams,
  telefonosUsables,
} from '../modelo.js';
import {
  $, $$, aviso, avisoError, chipAbordaje, chipAutorizacion, debounce, dialogo, fecha, fuentesVisibles, html, icono,
  insigniasFuentes, leyendaFuentes, montar, num, titulo,
} from '../ui.js';
import {
  administra, cargarLideres, chipsFaltan, chipsTipo, dialogoCompletar, faltanDe, formularioNuevaPersona, textoCedula, textoTelefono,
} from './comunes.js';

// Filtros que viajan en la URL (también los que solo llegan por enlace: Mi trabajo, tablero, mapa)
const FILTROS = ['q', 'zona', 'lugar_id', 'fuente', 'lista', 'etiqueta', 'con_cedula', 'con_telefono', 'varios_telefonos', 'precision',
  'asistio', 'consentimiento', 'lider', 'sexo', 'completitud_max', 'ids', 'ids_total', 'reunion_id', 'edad_min', 'edad_max',
  'puesto_id', 'votacion_estado', 'donde', 'con_puesto', 'con_mesa', 'abordaje_estado', 'abordado', 'contactado', 'ultimo_resultado',
  'sin_acercamiento_dias', 'proximo_vencido', 'canal_autorizado', 'requiere_actualizacion', 'situacion', 'creado_por',
  'actualizado_por', 'menor', 'area_id', 'poligono', 'tipo_documento', 'cedula_verificada', 'telefono_estado', 'estado_civil',
  'nivel_educativo', 'situacion_laboral', 'estrato', 'tenencia_vivienda', 'regimen_salud', 'lider_id', 'varios_lideres',
  'intervenida_en', 'tipo', 'jefe_hogar', 'ocupacion', 'perfil_profesional', 'con_correo',
  ...['cedula', 'telefono', 'sexo', 'edad', 'lugar', 'puesto', 'mesa', 'direccion', 'correo', 'estado_civil', 'ocupacion',
    'perfil_profesional', 'jefe_hogar', 'lider'].map((c) => `sin_${c}`)];
// Filtros con control propio (el resto se muestra como chip para verlo y quitarlo)
const CON_CONTROL = new Set(['q', 'zona', 'lugar_id', 'fuente', 'lista', 'etiqueta', 'con_cedula', 'con_telefono', 'varios_telefonos',
  'consentimiento', 'sexo', 'puesto_id', 'votacion_estado', 'donde', 'con_mesa', 'abordaje_estado', 'requiere_actualizacion',
  'situacion', 'creado_por', 'actualizado_por', 'menor', 'tipo', 'varios_lideres', 'precision', 'asistio', 'ids_total',
  'con_correo', 'sin_correo', 'sin_direccion', 'estado_civil', 'jefe_hogar', 'sin_jefe_hogar', 'ocupacion', 'perfil_profesional',
  'lider_id', 'sin_lider']);
const PARAMS_PUESTO = ['puesto_id', 'votacion_estado', 'donde'];
const PARAMS_TELEFONO = ['con_telefono', 'varios_telefonos'];
const PARAMS_CORREO = ['con_correo', 'sin_correo'];
const PARAMS_JEFE = ['jefe_hogar', 'sin_jefe_hogar'];
const PARAMS_LIDER = ['lider_id', 'sin_lider'];
// Los filtros que van plegados en «Más filtros» (votación, abordaje, autorización…): si alguno está puesto, se abre
const SECUNDARIOS = ['puesto_id', 'votacion_estado', 'donde', 'con_puesto', 'con_mesa', 'abordaje_estado', 'consentimiento',
  'requiere_actualizacion', 'situacion', 'etiqueta', 'fuente', 'lista', 'creado_por', 'actualizado_por', 'menor', 'varios_lideres',
  'precision', 'asistio'];

// Etiquetas de los chips de filtros que llegan por enlace
const OCULTOS = {
  // La lista de un hexágono lleva como mucho 500 ids: el chip dice cuántas de cuántas se ven
  ids: (v, f) => (Number(f.ids_total) > (v || '').split(',').length
    ? `Selección del mapa: ${num((v || '').split(',').length)} de ${num(Number(f.ids_total))}` : 'Selección del mapa'),
  area_id: (v) => `Zona guardada ${v}`,
  poligono: () => 'Zona dibujada en el mapa',
  edad_min: (v) => `Desde ${v} años`,
  edad_max: (v) => `Hasta ${v} años`,
  completitud_max: (v) => `Perfil hasta ${v} %`,
  reunion_id: (v) => `Asistentes de la reunión ${v}`,
  con_puesto: (v) => (v === '1' ? 'Con puesto' : 'Sin puesto'),
  abordado: (v) => (v === '1' ? 'Abordadas' : 'Sin abordar'),
  contactado: (v) => (v === '1' ? 'Contactadas' : 'Sin contactar'),
  ultimo_resultado: (v) => `Último resultado: ${v.replace(/_/g, ' ')}`,
  sin_acercamiento_dias: (v) => `Sin acercamiento en ${v} días`,
  proximo_vencido: () => 'Volver a contactar: vencido',
  canal_autorizado: (v) => `Autorizó ${v}`,
  lider_id: (v) => `Lideradas por ${nombresLideres[v] || `el líder ${v}`}`,
  lider: () => 'Solo líderes',
  sin_lider: () => 'Sin líder',
  intervenida_en: (v) => `Intervenidas en la reunión ${v}`,
};
// Los nombres de los líderes para el chip de `lider_id` (se cargan con la lista de líderes, solo A y K)
const nombresLideres = {};
const etiquetaOculto = (k, v, f) => (OCULTOS[k] ? OCULTOS[k](v, f)
  : k.startsWith('sin_') ? `Sin ${(ETIQUETAS_CAMPOS[k.slice(4)] || k.slice(4)).toLowerCase()}` : `${k.replace(/_/g, ' ')}: ${v}`);

const POR_PAGINA = 50;
const TOPE_PLANILLERO = 1000;

export async function vistaPersonas(el, { q, ir }) {
  const f = Object.fromEntries(FILTROS.filter((k) => q.get(k)).map((k) => [k, q.get(k)]));
  let orden = q.get('orden') || 'nombre', pagina = Number(q.get('pagina') || 1);
  const cat = await api.catalogos();
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const adm = administra();
  const esP = sesion.rol === 'planillero';
  const completa = puede('personas.editar');
  const opciones = (lista, valor) => lista.map(([v, t]) => html`<option value="${v}" ${String(valor ?? '') === String(v) ? 'selected' : ''}>${t}</option>`);

  // Valores compuestos: puesto (id, «sin puesto», «por confirmar», «otro municipio»), teléfono y rango de edad
  const valorPuestoF = () => (f.puesto_id != null ? `p:${f.puesto_id}` : f.votacion_estado ? `e:${f.votacion_estado}` : f.donde ? `d:${f.donde}` : '');
  const valorTelF = () => (f.varios_telefonos ? 'varios' : f.con_telefono === '1' ? 'con' : f.con_telefono === '0' ? 'sin' : '');
  const valorRangoF = () => RANGOS_EDAD.find((r) => {
    const x = rangoAParams(r);
    return String(x.edad_min ?? '') === String(f.edad_min ?? '') && String(x.edad_max ?? '') === String(f.edad_max ?? '');
  }) || '';
  const valorCorreoF = () => (f.con_correo === '1' ? 'con' : f.sin_correo === '1' || f.con_correo === '0' ? 'sin' : '');
  const valorJefeF = () => (f.sin_jefe_hogar === '1' ? 'sin' : ['si', 'no'].includes(f.jefe_hogar) ? f.jefe_hogar : '');
  const valorLiderF = () => (f.sin_lider === '1' ? 'sin' : f.lider_id || '');
  // «Liderado por» (A y K): la lista de líderes y concejales llega después; mientras, el elegido se ve por su nombre
  let lideresF = null;
  const opcionesLider = () => {
    const actual = valorLiderF();
    const ls = (lideresF || []).filter((l) => l.marcado || String(l.id) === String(f.lider_id));
    const conActual = actual && actual !== 'sin' && !ls.some((l) => String(l.id) === actual)
      ? [[actual, nombresLideres[actual] || `Líder ${actual}`]] : [];
    return opciones([['', 'Liderado por'], ['sin', 'Sin líder'], ...conActual,
      ...ls.map((l) => [String(l.id), `${l.nombre}${l.tipo ? ` (${TIPOS_PERSONA[l.tipo]})` : ''}`])], actual);
  };
  const secundariosActivos = () => SECUNDARIOS.filter((k) => f[k] != null && f[k] !== '').length;
  const ocultos = () => Object.keys(f).filter((k) => !CON_CONTROL.has(k) && !(['edad_min', 'edad_max'].includes(k) && valorRangoF()));
  const activos = () => Object.keys(f).filter((k) => k !== 'q' && k !== 'ids_total' && f[k] != null && f[k] !== '').length;
  const usuarios = (cat.usuarios || []).map((u) => [u.id, u.nombre || u.usuario]);

  montar(el, html`
    <div class="cabecera">
      <div><h1>Habitantes</h1><div class="sub" id="total">Cargando…</div></div>
      <div class="acciones">
        ${adm ? html`<button class="btn" id="ver-lideres" title="Cuántas personas lidera cada líder o concejal y cuáles trae más de uno">Líderes</button>` : ''}
        ${puede('exportar') ? html`<button class="btn" id="exportar" title="Exporta lo filtrado; omite a quien marcó «No autorizó» el tratamiento de sus datos">${icono('descargar')} Exportar a Excel</button>` : ''}
        ${adm && puede('personas.crear') ? html`<button class="btn" id="nuevo-votante" title="Registrar un votante y buscar al líder o concejal que lo trajo">${icono('mas')} Nuevo votante</button>` : ''}
        ${puede('personas.crear') ? html`<button class="btn primario" id="nueva">${icono('mas')} Nueva persona</button>` : ''}
      </div>
    </div>
    <div class="filtros plegables" id="filtros">
      <label class="buscador"><span class="sr">Buscar</span>${icono('buscar')}<input class="entrada" id="q" type="search" placeholder="Nombre, cédula, teléfono, dirección o ficha" value="${f.q || ''}"></label>
      <button class="btn boton-filtros" id="ver-filtros" aria-expanded="false" aria-controls="mas-filtros">${icono('filtro')} <span id="n-filtros">Filtros</span></button>
      <div class="mas-filtros" id="mas-filtros">
        <select class="entrada" data-f="con_cedula" aria-label="Cédula">${opciones([['', 'Cédula'], ['1', 'Con cédula'], ['0', 'Sin cédula']], f.con_cedula)}</select>
        <select class="entrada" data-f="sexo" aria-label="Sexo">${opciones([['', 'Sexo'], ...Object.entries(SEXOS), ['sin', 'Sin dato']], f.sexo)}</select>
        <select class="entrada" id="f-edad" aria-label="Rango de edad">${opciones([['', 'Edad'], ...RANGOS_EDAD.map((r) => [r, `${r} años`])], valorRangoF())}</select>
        <select class="entrada" id="f-tel" aria-label="Teléfono">${opciones([['', 'Teléfono'], ['con', 'Con teléfono usable'], ['varios', 'Varios números'], ['sin', 'Sin teléfono']], valorTelF())}</select>
        <select class="entrada" id="f-correo" aria-label="Correo electrónico">${opciones([['', 'Correo'], ['con', 'Con correo'], ['sin', 'Sin correo']], valorCorreoF())}</select>
        <select class="entrada" data-f="sin_direccion" aria-label="Dirección">${opciones([['', 'Dirección'], ['1', 'Sin dirección']], f.sin_direccion)}</select>
        <select class="entrada" data-f="lugar_id" aria-label="Barrio o vereda">${opciones([['', 'Barrio / vereda'], ['0', 'Sin barrio o vereda'], ...(cat.lugares || []).map((l) => [l.id, titulo(l.nombre) + (l.tipo !== 'barrio' ? ` · ${l.tipo.replace('_', ' ')}` : '')])], f.lugar_id)}</select>
        <select class="entrada" data-f="zona" aria-label="Zona urbana o rural">${opciones([['', 'Zona'], ['urbana', 'Urbana (casco)'], ['rural', 'Rural'], ['sin', 'Sin zona']], f.zona)}</select>
        ${adm ? html`<select class="entrada" data-f="tipo" aria-label="Tipo de persona">${opciones([['', 'Líder / votante'], ...Object.entries(TIPOS_PERSONA), ['sin_tipo', 'Sin tipo']], f.tipo)}</select>
          <select class="entrada" id="f-lider" aria-label="Liderado por">${opcionesLider()}</select>` : ''}
        <label class="campo-filtro"><span class="sr">Perfil profesional</span><input class="entrada" data-texto="perfil_profesional" type="search" maxlength="160" placeholder="Perfil profesional" value="${f.perfil_profesional || ''}" enterkeyhint="search"></label>
        <label class="campo-filtro"><span class="sr">Ocupación</span><input class="entrada" data-texto="ocupacion" type="search" maxlength="120" placeholder="Ocupación" value="${f.ocupacion || ''}" enterkeyhint="search"></label>
        <select class="entrada" data-f="estado_civil" aria-label="Estado civil">${opciones([['', 'Estado civil'], ...ESTADOS_CIVILES.map((e) => [e, e]), ['sin', 'Sin dato']], f.estado_civil)}</select>
        <select class="entrada" id="f-jefe" aria-label="Jefe de hogar">${opciones([['', 'Jefe de hogar'], ['si', 'Jefe de hogar: sí'], ['no', 'Jefe de hogar: no'], ['sin', 'Jefe de hogar: sin dato']], valorJefeF())}</select>
        <select class="entrada" id="orden" aria-label="Orden">${opciones([['nombre', 'Orden: nombre'], ['-completitud', 'Menos completos'], ['completitud', 'Más completos'], ['por_llamar', 'Sin abordar primero'], ['abordaje_reciente', 'Abordaje reciente'], ['lugar', 'Por barrio y dirección'], ['contacto', 'Contacto reciente'], ['reciente', 'Editados recientemente']], orden)}</select>
        <details class="filtros-secundarios" id="filtros-secundarios" ${secundariosActivos() ? 'open' : ''}>
          <summary>Más filtros: votación, abordaje, autorización…<span id="n-secundarios">${secundariosActivos() ? ` (${secundariosActivos()})` : ''}</span></summary>
          <div class="filtros-secundarios-cuerpo">
            <select class="entrada" id="f-puesto" aria-label="Puesto de votación">${opciones([['', 'Puesto'], ['p:0', 'Sin puesto'], ['e:por_confirmar', 'Por confirmar'], ['d:otro_municipio', 'Otro municipio'], ['d:no_inscrito', 'No inscrito'],
              ...(cat.puestos || []).map((x) => [`p:${x.id}`, `${x.codigo ? x.codigo + ' · ' : ''}${titulo(x.nombre)}`])], valorPuestoF())}</select>
            <select class="entrada" data-f="con_mesa" aria-label="Mesa">${opciones([['', 'Mesa'], ['1', 'Con mesa'], ['0', 'Sin mesa']], f.con_mesa)}</select>
            <select class="entrada" data-f="abordaje_estado" aria-label="Abordaje">${opciones([['', 'Abordaje'], ...Object.entries(ESTADOS_ABORDAJE)], f.abordaje_estado)}</select>
            <select class="entrada" data-f="consentimiento" aria-label="Autorización">${opciones([['', 'Autorización'], ['si', 'Autorizó'], ['pendiente', 'Pendiente'], ['no', 'No autorizó']], f.consentimiento)}</select>
            <select class="entrada" data-f="requiere_actualizacion" aria-label="Actualización">${opciones([['', 'Actualización'], ['1', 'Pendientes de actualizar']], f.requiere_actualizacion)}</select>
            <select class="entrada" data-f="situacion" aria-label="Situación">${opciones([['', 'Vigentes'], ['todas', 'Todas las situaciones'], ...Object.entries(SITUACIONES).filter(([k]) => k !== 'activa')], f.situacion)}</select>
            ${(cat.etiquetas || []).length ? html`<select class="entrada" data-f="etiqueta" aria-label="Necesidad o etiqueta">${opciones([['', 'Necesidad / etiqueta'], ...cat.etiquetas.map((e) => [e.id, e.nombre])], f.etiqueta)}</select>` : ''}
            ${adm ? html`
              <select class="entrada" data-f="fuente" aria-label="Fuente">${opciones([['', 'Fuente'], ['tramites', 'Base de trámites'], ['cedulas', 'Base con cédula'], ['ambas', 'En las dos'], ['general', 'Base general'], ['planilla', 'Planilla de campo'], ['reunion', 'Registradas en reunión'], ['manual', 'Registro manual']], f.fuente)}</select>
              ${(cat.listas || []).length ? html`<select class="entrada" data-f="lista" aria-label="Lista">${opciones([['', 'Lista'], ...cat.listas.map((l) => [l, l])], f.lista)}</select>` : ''}
              ${usuarios.length ? html`<select class="entrada" data-f="creado_por" aria-label="Creado por">${opciones([['', 'Creado por'], ...usuarios], f.creado_por)}</select>
                <select class="entrada" data-f="actualizado_por" aria-label="Actualizado por">${opciones([['', 'Actualizado por'], ...usuarios], f.actualizado_por)}</select>` : ''}
              <select class="entrada" data-f="menor" aria-label="Menores">${opciones([['', 'Edad legal'], ['1', 'Menores de edad'], ['0', 'Sin menores']], f.menor)}</select>
              <select class="entrada" data-f="varios_lideres" aria-label="Captación">${opciones([['', 'Captación'], ['1', 'Lideradas por más de uno']], f.varios_lideres)}</select>
              <select class="entrada" data-f="precision" aria-label="Ubicación">${opciones([['', 'Ubicación'], ['exacta', 'Dirección exacta'], ['aproximada', 'Aproximada'], ['ubicada', 'Con ubicación'], ['sin', 'Sin ubicar']], f.precision)}</select>
              <select class="entrada" data-f="asistio" aria-label="Reuniones">${opciones([['', 'Reuniones'], ['1', 'Asistió'], ['0', 'Sin reunión']], f.asistio)}</select>` : ''}
          </div>
        </details>
      </div>
      <div class="chips" id="chips-ocultos"></div>
    </div>
    ${adm ? leyendaFuentes(fuentesVisibles(true)) : ''}
    <div class="envoltura-tabla"><table class="tabla tabla-tarjetas tabla-personas"><thead><tr>
      <th>Nombre</th><th>Cédula</th><th>Sexo y edad</th><th>Teléfono y correo</th><th>Dirección y barrio</th>${adm ? html`<th>Líder / votante · Liderado por</th>` : ''}<th>Perfil y ocupación</th><th>Faltan</th><th>Completitud</th>${completa ? html`<th><span class="sr">Acciones</span></th>` : ''}
    </tr></thead><tbody id="filas"></tbody></table></div>
    <div class="paginacion" id="paginacion"></div>`);

  const columnas = 8 + (adm ? 1 : 0) + (completa ? 1 : 0);
  let datos = { total: 0, filas: [], por_pagina: POR_PAGINA };

  function pintarChips() {
    montar($('#chips-ocultos', el), html`${ocultos().map((k) => html`<button class="chip rojo" data-quitar="${k}" aria-label="Quitar filtro: ${etiquetaOculto(k, f[k], f)}">${etiquetaOculto(k, f[k], f)} ✕</button>`)}`);
    const n = activos();
    $('#n-filtros', el).textContent = n ? `Filtros (${n})` : 'Filtros';
    const ns = secundariosActivos();
    $('#n-secundarios', el).textContent = ns ? ` (${ns})` : '';
  }

  // Las columnas siguen los datos principales de la ficha. P recibe de ellos solo lo que no identifica: sin correo,
  // dirección ni fecha exacta (los ve en la ficha)
  const jefe = (v) => (v === true ? 'Jefe de hogar' : v === false ? 'No es jefe de hogar' : null);
  function celdas(p, i) {
    const ced = textoCedula(p) || (p.tiene_cedula ? 'Con cédula' : null);
    const tel = textoTelefono(p);
    const edad = p.edad_efectiva != null ? `${p.edad_efectiva} años` : p.rango_edad ? `${p.rango_edad} años` : (p.edad != null ? `${p.edad} años` : null);
    const perfil = [p.perfil_profesional, p.ocupacion].filter(Boolean);
    const hogar = [p.estado_civil, jefe(p.jefe_hogar)].filter(Boolean).join(' · ');
    const lideres = Array.isArray(p.lideres) ? p.lideres : [];
    const sit = p.situacion?.estado && p.situacion.estado !== 'activa' ? p.situacion.estado : typeof p.situacion === 'string' && p.situacion !== 'activa' ? p.situacion : null;
    return html`
      <td data-titulo="Nombre"><a class="nombre" href="/personas/${p.id}" data-ruta>${p.nombre}</a>
        <div class="chips chips-fila">${ced ? '' : html`<span class="chip ambar">Sin cédula</span>`}${p.abordaje !== undefined ? chipAbordaje(p.abordaje) : ''}${p.consentimiento ? chipAutorizacion(p, { conCanales: false }) : ''}
          ${p.requiere_actualizacion ? html`<span class="chip ambar">Pendiente de actualizar</span>` : ''}${p.menor ? html`<span class="chip rojo">Menor</span>` : ''}
          ${sit ? html`<span class="chip rojo">${SITUACIONES[sit] || sit}</span>` : ''}${p.lideres_n > 1 ? html`<span class="chip ambar" title="Más de un líder la está captando">${p.lideres_n} líderes</span>` : ''}
          ${adm ? insigniasFuentes(p.fuentes) : ''}</div></td>
      <td data-titulo="Cédula">${ced || html`<span class="sec">—</span>`}</td>
      <td data-titulo="Sexo y edad">${[SEXOS[p.sexo], edad].filter(Boolean).join(' · ') || html`<span class="sec">—</span>`}${p.fecha_nacimiento ? html`<div class="sec">Nació el ${fecha(p.fecha_nacimiento)}</div>` : ''}</td>
      <td data-titulo="Teléfono y correo">${tel || html`<span class="sec">Sin teléfono</span>`}${p.telefonos_n > 1 ? html` <span class="chip borde" title="Números usables">${p.telefonos_n}</span>` : ''}
        ${p.correo ? html`<div class="sec dato-largo">${p.correo}</div>` : p.tiene_correo ? html`<div class="sec">Con correo</div>` : ''}</td>
      <td data-titulo="Dirección y barrio">${p.direccion ? html`<span class="dato-largo">${p.direccion}</span>` : ''}${p.lugar ? html`<div class="${p.direccion ? 'sec' : ''}">${titulo(p.lugar)}</div>` : p.direccion ? '' : html`<span class="sec">—</span>`}<div class="sec">${p.zona === 'rural' ? 'Rural' : p.zona === 'urbana' ? 'Urbana (casco)' : ''}</div></td>
      ${adm ? html`<td data-titulo="Líder / votante · Liderado por">${chipsTipo(p)}${lideres.length ? html`<div class="liderado-fila">Liderado por ${lideres.map((l, j) => html`${j ? ', ' : ''}<a href="/personas/${l.id}" data-ruta>${l.nombre}</a>`)}</div>` : ''}${!Object.keys(TIPOS_PERSONA).some((k) => p[k] === true) && !lideres.length ? html`<span class="sec">—</span>` : ''}</td>` : ''}
      <td data-titulo="Perfil y ocupación">${perfil.length ? html`<span class="dato-largo">${perfil.join(' · ')}</span>` : html`<span class="sec">—</span>`}${hogar ? html`<div class="sec">${hogar}</div>` : ''}</td>
      <td data-titulo="Faltan">${chipsFaltan(faltanDe(p), { principales: true }) || html`<span class="sec">Nada</span>`}</td>
      <td data-titulo="Completitud"><span class="barra-comp"><i><b style="width:${Number(p.completitud) || 0}%"></b></i>${Number(p.completitud) || 0} %</span></td>
      ${completa ? html`<td class="celda-acciones">${p.consentimiento === 'no' && !adm ? '' : html`<button class="btn chico" data-completar="${i}">${icono('completar')} Completar</button>`}</td>` : ''}`;
  }

  let turno = 0;
  async function cargar() {
    // Una búsqueda que se dispara después de salir de la vista no debe tocar la URL ni el DOM de otra
    if (!el.isConnected) return;
    const mio = ++turno;
    const params = { ...f, orden, pagina, por_pagina: POR_PAGINA };
    history.replaceState({}, '', url('/personas?') + new URLSearchParams(Object.entries(params).filter(([k, v]) => v && !(k === 'pagina' && v === 1) && k !== 'por_pagina')));
    pintarChips();
    montar($('#filas', el), html`${Array.from({ length: 8 }, () => html`<tr class="esqueleto-fila"><td colspan="${columnas}"><div class="esqueleto" style="height:18px"></div></td></tr>`)}`);
    let d;
    try {
      d = await api.get('/api/personas', params);
    } catch (e) {
      if (mio !== turno || !el.isConnected) return;
      montar($('#filas', el), html`<tr><td colspan="${columnas}"><div class="vacio"><b>No se pudo cargar</b>${e.message}</div></td></tr>`);
      $('#total', el).textContent = '';
      throw e;
    }
    if (mio !== turno || !el.isConnected) return; // llegó tarde: ya se pidió otra página u otros filtros
    datos = d;
    const recortada = f.ids && Number(f.ids_total) > d.total;
    $('#total', el).textContent = recortada
      ? `${num(d.total)} de las ${num(Number(f.ids_total))} personas de la selección del mapa (llega hasta 500)`
      : `${num(d.total)} ${d.total === 1 ? 'persona' : 'personas'} con estos filtros`;
    if (d.filas.length) montar($('#filas', el), html`${d.filas.map((p, i) => html`<tr data-id="${p.id}" data-i="${i}">${celdas(p, i)}</tr>`)}`);
    else {
      const buscado = (f.q || '').trim();
      montar($('#filas', el), html`<tr><td colspan="${columnas}"><div class="vacio"><b>Nadie coincide</b>${buscado ? 'No aparece en la base.' : 'Pruebe con menos filtros.'}
        ${buscado && puede('personas.crear') ? html`<div style="margin-top:12px"><button class="btn primario" data-nueva-buscado>${icono('mas')} Nueva persona con lo buscado</button></div>` : ''}</div></td></tr>`);
    }
    const porPagina = d.por_pagina || POR_PAGINA;
    const tope = d.tope ?? (esP ? TOPE_PLANILLERO : null);
    const totalVisible = tope ? Math.min(d.total, tope) : d.total;
    const paginas = Math.max(1, Math.ceil(totalVisible / porPagina));
    const enTope = tope && d.total > tope && pagina >= paginas;
    montar($('#paginacion', el), html`<span>Página ${pagina} de ${num(paginas)}</span>
      ${enTope ? html`<span class="aviso-tope">Se ven las primeras ${num(tope)}; filtre por barrio.</span>` : ''}
      <span class="botones-pagina"><button class="btn chico" data-p="${pagina - 1}" ${pagina <= 1 ? 'disabled' : ''}>← Anterior</button>
      <button class="btn chico" data-p="${pagina + 1}" ${pagina >= paginas ? 'disabled' : ''}>Siguiente →</button></span>`);
  }

  // La fila se actualiza en su lugar con la ficha guardada: sin recargar ni perder la posición
  function actualizarFila(i, ficha) {
    const vieja = datos.filas[i];
    if (!vieja || !ficha) return;
    const usables = telefonosUsables(ficha);
    const nueva = { ...vieja };
    for (const k of ['nombre', 'completitud', 'consentimiento', 'sexo', 'rango_edad', 'requiere_actualizacion', 'menor', 'faltan', 'lugar',
      'votacion_estado', 'perfil_profesional', 'ocupacion', 'estado_civil', 'jefe_hogar', 'zona']) {
      if (ficha[k] !== undefined) nueva[k] = ficha[k];
    }
    // Lo que la fila de P no trae (correo, dirección, fecha exacta) tampoco se copia de su ficha
    for (const k of ['correo', 'direccion', 'fecha_nacimiento', 'edad_efectiva', ...Object.keys(TIPOS_PERSONA), 'lideres']) {
      if (k in vieja && ficha[k] !== undefined) nueva[k] = ficha[k];
    }
    if ('tiene_correo' in vieja && ficha.correo !== undefined) nueva.tiene_correo = !!ficha.correo;
    if (ficha.abordaje !== undefined) nueva.abordaje = ficha.abordaje;
    if (ficha.lugar_nombre) nueva.lugar = ficha.lugar_nombre;
    if (ficha.cedula) { if ('cedula' in vieja) nueva.cedula = ficha.cedula; nueva.cedula_ult3 = String(ficha.cedula).slice(-3); nueva.tiene_cedula = true; }
    if (usables.length) {
      if ('telefono' in vieja && adm) nueva.telefono = usables[0].numero;
      else nueva.telefono_mascara = enmascarar(usables[0].numero);
      nueva.telefonos_n = usables.length;
    }
    if (ficha.votacion) { nueva.votacion = ficha.votacion; nueva.mesa = ficha.votacion.mesa_texto ?? ficha.votacion.mesa ?? nueva.mesa; nueva.puesto = null; }
    if (!Array.isArray(ficha.faltan)) delete nueva.faltan;
    datos.filas[i] = nueva;
    const tr = $(`#filas tr[data-i="${i}"]`, el);
    if (tr) { montar(tr, celdas(nueva, i)); tr.classList.add('recien'); setTimeout(() => tr.classList.remove('recien'), 1600); }
  }

  async function completar(i) {
    const fila = datos.filas[i];
    if (!fila) return;
    let ficha;
    try { ficha = await api.get(`/api/personas/${fila.id}`); } catch (e) { avisoError(e); return; }
    if (!el.isConnected) return;
    const r = await dialogoCompletar(ficha, cat, { siguiente: true });
    if (!r) return;
    actualizarFila(i, r.ficha);
    if (!r.siguiente) return;
    if (i + 1 < datos.filas.length) {
      $(`#filas tr[data-i="${i + 1}"]`, el)?.scrollIntoView({ block: 'center' });
      completar(i + 1);
    } else if (!$('#paginacion [data-p]:last-child', el)?.disabled) {
      pagina += 1;
      await cargar();
      el.scrollIntoView();
      if (datos.filas.length) completar(0);
    } else aviso('Era la última persona de la lista');
  }

  function nuevaConBuscado() {
    const t = (f.q || '').trim();
    const dig = t.replace(/\D/g, '');
    const prellenado = /\d/.test(t) && dig.length >= 5 ? (/^3\d{9}$/.test(dig) ? { telefono: dig } : { cedula: dig }) : { nombre: t };
    formularioNuevaPersona({ cat, prellenado, alCrear: (p) => ir(`/personas/${p.id}`) });
  }

  const buscar = debounce((e) => { f.q = e.target.value.trim() || undefined; if (!f.q) delete f.q; pagina = 1; cargar().catch(avisoError); }, 300);
  $('#q', el).addEventListener('input', buscar);
  const recargar = () => { pagina = 1; cargar().catch(avisoError); };
  for (const s of $$('[data-f]', el)) s.addEventListener('change', () => { if (s.value) f[s.dataset.f] = s.value; else delete f[s.dataset.f]; recargar(); });
  $('#f-edad', el).addEventListener('change', (e) => {
    delete f.edad_min; delete f.edad_max;
    Object.assign(f, Object.fromEntries(Object.entries(rangoAParams(e.target.value)).map(([k, v]) => [k, String(v)])));
    recargar();
  });
  $('#f-puesto', el).addEventListener('change', (e) => {
    for (const k of PARAMS_PUESTO) delete f[k];
    const [tipo, v] = e.target.value.split(':');
    if (tipo === 'p') f.puesto_id = v; else if (tipo === 'e') f.votacion_estado = v; else if (tipo === 'd') f.donde = v;
    recargar();
  });
  $('#f-tel', el).addEventListener('change', (e) => {
    for (const k of PARAMS_TELEFONO) delete f[k];
    if (e.target.value === 'con') f.con_telefono = '1'; else if (e.target.value === 'sin') f.con_telefono = '0'; else if (e.target.value === 'varios') f.varios_telefonos = '1';
    recargar();
  });
  $('#f-correo', el).addEventListener('change', (e) => {
    for (const k of PARAMS_CORREO) delete f[k];
    if (e.target.value === 'con') f.con_correo = '1'; else if (e.target.value === 'sin') f.sin_correo = '1';
    recargar();
  });
  $('#f-jefe', el).addEventListener('change', (e) => {
    for (const k of PARAMS_JEFE) delete f[k];
    if (e.target.value === 'sin') f.sin_jefe_hogar = '1'; else if (e.target.value) f.jefe_hogar = e.target.value;
    recargar();
  });
  $('#f-lider', el)?.addEventListener('change', (e) => {
    for (const k of PARAMS_LIDER) delete f[k];
    if (e.target.value === 'sin') f.sin_lider = '1'; else if (e.target.value) f.lider_id = e.target.value;
    recargar();
  });
  // Perfil profesional y ocupación (texto que contiene): se aplican al terminar de escribir (Enter o al salir del campo),
  // no letra por letra: cada consulta cuenta en el límite de frecuencia y en el presupuesto diario de P
  for (const x of $$('[data-texto]', el)) {
    const aplicar = () => {
      const v = x.value.trim();
      if ((f[x.dataset.texto] || '') === v || (v && v.length < 2)) return;
      if (v) f[x.dataset.texto] = v; else delete f[x.dataset.texto];
      recargar();
    };
    x.addEventListener('change', aplicar);
    x.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); aplicar(); } });
    x.addEventListener('search', aplicar); // la ✕ del campo de búsqueda lo vacía
  }
  $('#orden', el).addEventListener('change', (e) => { orden = e.target.value; recargar(); });
  $('#ver-filtros', el).addEventListener('click', (e) => {
    const abierto = $('#filtros', el).classList.toggle('abiertos');
    e.currentTarget.setAttribute('aria-expanded', abierto);
  });
  $('#chips-ocultos', el).addEventListener('click', (e) => {
    const b = e.target.closest('[data-quitar]');
    if (!b) return;
    delete f[b.dataset.quitar];
    if (b.dataset.quitar === 'ids') delete f.ids_total;
    recargar();
  });
  $('#paginacion', el).addEventListener('click', (e) => { const b = e.target.closest('[data-p]'); if (b && !b.disabled) { pagina = Number(b.dataset.p); cargar().catch(avisoError); el.scrollIntoView(); } });
  // El nombre es un enlace (teclado, lector de pantalla, abrir en otra pestaña); el resto de la fila también abre la ficha
  $('#filas', el).addEventListener('click', (e) => {
    const c = e.target.closest('[data-completar]');
    if (c) { completar(Number(c.dataset.completar)); return; }
    if (e.target.closest('[data-nueva-buscado]')) { nuevaConBuscado(); return; }
    if (e.target.closest('a, button')) return;
    const tr = e.target.closest('tr[data-id]');
    if (tr) ir(`/personas/${tr.dataset.id}`);
  });
  $('#exportar', el)?.addEventListener('click', async () => {
    try { await descargar('/api/exportar.xlsx', f); aviso('Exportación lista (quedó registrada en la auditoría)'); } catch (e) { aviso(e.message, 'error'); }
  });
  $('#nueva', el)?.addEventListener('click', () => formularioNuevaPersona({ cat, alCrear: (p) => ir(`/personas/${p.id}`) }));
  $('#nuevo-votante', el)?.addEventListener('click', () => formularioNuevaPersona({ cat, prellenado: { tipo: 'votante' }, alCrear: (p) => ir(`/personas/${p.id}`) }));
  $('#ver-lideres', el)?.addEventListener('click', () => dialogoLideres(ir).catch(avisoError));
  // Los líderes y concejales para «Liderado por» (A y K). Si no llegan, el filtro sigue con «Sin líder» y el elegido
  if (adm) {
    cargarLideres().then((r) => {
      lideresF = r.lideres || [];
      for (const l of lideresF) nombresLideres[l.id] = l.nombre;
      const s = $('#f-lider', el);
      if (s && el.isConnected) montar(s, opcionesLider());
    }).catch(() => {});
  }
  await cargar();
  return () => buscar.cancel();
}

// Los líderes y concejales (A y K): cuántas personas trajo cada uno, cuántas son votantes y cuántas trae también otro
async function dialogoLideres(ir) {
  const r = await cargarLideres();
  const ls = r.lideres || [];
  for (const l of ls) nombresLideres[l.id] = l.nombre;
  const { el: d, cerrar } = dialogo({
    titulo: 'Líderes y concejales',
    ancho: true,
    cuerpo: html`<p class="sec" style="margin-top:0">Cada persona puede estar liderada por uno o más líderes o concejales (se asignan en su ficha o al registrarla).
        ${r.personas_con_varios ? html`<a href="/personas?varios_lideres=1" data-ir>${num(r.personas_con_varios)} ${r.personas_con_varios === 1 ? 'persona tiene' : 'personas tienen'} más de un líder</a>.` : 'Nadie tiene más de un líder.'}</p>
      ${ls.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Líder o concejal</th><th>Barrio / vereda</th><th>Lidera</th><th>Votantes</th><th>También con otro líder</th></tr></thead>
        <tbody>${ls.map((l) => html`<tr style="cursor:default"><td><a href="/personas/${l.id}" data-ir>${l.nombre}</a> ${l.tipo ? html`<span class="chip ${l.tipo === 'concejal' ? 'azul' : 'rojo'}">${TIPOS_PERSONA[l.tipo]}</span>` : html`<span class="chip ambar">Ya no marcado</span>`}</td>
          <td>${l.lugar ? titulo(l.lugar) : html`<span class="sec">—</span>`}</td>
          <td>${l.traidas ? html`<a href="/personas?lider_id=${l.id}" data-ir>${num(l.traidas)}</a>` : '0'}</td>
          <td>${l.votantes ? html`<a href="/personas?lider_id=${l.id}&tipo=votante" data-ir>${num(l.votantes)}</a>` : '0'}</td>
          <td>${l.compartidas ? html`<a href="/personas?lider_id=${l.id}&varios_lideres=1" data-ir>${num(l.compartidas)}</a>` : '0'}</td></tr>`)}</tbody></table></div>`
        : html`<div class="vacio"><b>Aún no hay líderes</b>Marque a una persona como «Líder» o «Concejal» en su ficha.</div>`}`,
  });
  // Los enlaces cierran el diálogo y abren la vista (una lista filtrada se vuelve a pintar entera)
  d.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-ir]');
    if (!a) return;
    e.preventDefault();
    cerrar();
    ir(a.getAttribute('href'));
  });
}
