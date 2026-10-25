// Inventario navegable de la torre para el recorrido (equipo C; especificación de integración, 6.5 y 16.4).
// Lee web/data/torre_inventario.json (forma web del 10.2, con sus partes ya juntas), la planta y la matriz de cumplimiento,
// y arma: las unidades con su nivel y su recinto, la ficha de cada unidad (clase de riesgo, registro, exigencias, precio,
// mantenimiento, contenido e implementos internos), la ficha de un recinto, la lista de dotación del recinto actual y el
// buscador con filtros, totales e «Ir a». Todos los textos de los datos pasan por textos.esc (13.6): nada de rutas ni claves.
import { fmtCOP, fmtN } from '../../core.js';
import { verificacion as nivelVerificacion } from './textos.js';

export const NIVELES = ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB'];
export const NOMBRE_NIVEL = { EXT: 'Exteriores', P1: 'Piso 1', P2: 'Piso 2', P3: 'Piso 3', P4: 'Piso 4', BT: 'Bloque técnico', CUB: 'Cubierta' };
const SERVICIOS = {
  urgencias: 'Urgencias', hospitalizacion: 'Hospitalización', partos: 'Atención del parto', esterilizacion: 'Esterilización',
  expansion_emergencias: 'Sala de expansión', sala_expansion: 'Sala de expansión', consulta_externa: 'Consulta externa', odontologia: 'Odontología',
  telemedicina: 'Telemedicina', vacunacion: 'Vacunación', farmacia: 'Servicio farmacéutico', terapias: 'Terapias', laboratorio: 'Laboratorio clínico',
  toma_muestras: 'Toma de muestras', imagenes: 'Imágenes diagnósticas', tic_apoyo: 'TIC y apoyo', fijo: 'Equipamiento fijo e industrial',
  vestibulo: 'Vestíbulo y admisiones', bloque_tecnico: 'Bloque técnico', cubierta: 'Cubierta técnica', exteriores: 'Exteriores',
  circulacion: 'Circulaciones', apoyo_tecnico: 'Apoyo técnico',
};
export const CAPAS = { dotacion: 'Dotación', fijo: 'Equipamiento fijo', laboratorio: 'Laboratorio (comodato, programa u opcional)', cierre_brechas: 'Cierre de brechas propuesto', infraestructura: 'Infraestructura', contexto: 'Contexto (no es de la torre)' };
const ESTADOS_U = { en_dotacion: 'En la dotación', cierre_brechas_propuesto: 'Faltante: cierre propuesto', infraestructura: 'Infraestructura de obra', contexto: 'Contexto', fuera_de_la_torre: 'Fuera de la torre' };
export const ESTADOS_R = { cumple: 'Cumple', parcial: 'Parcial', falta: 'Falta', documento_pendiente: 'Documento pendiente', no_aplica: 'No aplica' };
const CLASES = { I: 'I', IIa: 'IIa', IIb: 'IIb', III: 'III', ivd: 'diagnóstico in vitro', no_dm: 'no es dispositivo médico', por_confirmar: 'por confirmar' };
const PRIORIDAD = { habilitacion: 'exigida para la habilitación', recomendado: 'recomendado', por_confirmar: 'por confirmar', no_aplica: 'no aplica' };
const TIPO_PRECIO = {
  referencia_secop_ajustada_ipc: 'referencia de compras públicas (SECOP) llevada a pesos de 2026 con el IPC', estimacion: 'estimación', calculo_propio: 'cálculo propio',
  cotizacion: 'cotización', dato_oficial: 'dato oficial',
};
const ANCLAJE = { ruedas_con_freno: 'ruedas con freno', anclado: 'anclado a la estructura', apoyado: 'apoyado, sin anclaje', sobre: 'sobre otro mueble', dentro: 'dentro de otro elemento', pared: 'fijo a la pared', colgado: 'colgado', empotrado: 'empotrado' };
const MONTAJE = { piso: 'en el piso', pared: 'en la pared', sobre: 'sobre otro mueble', dentro: 'dentro de otro elemento', cielo: 'en el cielo raso', en_nucleo: 'en el núcleo' };
const palabras = (s) => String(s ?? '').replace(/_/g, ' ');
// vías del registro INVIMA tal como vienen en los datos («automatico», «evaluacion_tecnica») → en palabras y con tildes
const via = (s) => palabras(s).replace(/\bautomatico\b/g, 'automático').replace(/\bevaluacion tecnica\b/g, 'evaluación técnica').replace(/\bno aplica\b/g, 'no aplica');
function dentroPol(x, y, pol) {
  let d = false;
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) {
    const [xi, yi] = pol[i], [xj, yj] = pol[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d;
  }
  return d;
}
const normal =(s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// ---------------------------------------------------------------- modelo
export function crearInventario(inv, { plantas = null, habilitacion = null, textos } = {}) {
  const { esc, escH, limpio } = textos;
  const lineas = inv?.lineas || [], cols = inv?.columnas_unidades || [], filas = inv?.unidades || [], extra = inv?.unidades_extra || {};
  const col = Object.fromEntries(cols.map((c, i) => [c, i]));
  const tramos = Object.entries(inv?.por_nivel || {});
  const nivelDe = (i) => { for (const [k, [a, b]] of tramos) if (i >= a && i < b) return k; return null; };
  // recintos de la planta (nombre, nivel, servicio, áreas) con sus subrecintos
  const recintos = new Map();
  for (const n of plantas?.niveles || []) for (const r of n.recintos || []) {
    recintos.set(r.id, { ...r, nivel: n.id });
    for (const s of r.subrecintos || []) recintos.set(s.id, { ...s, ambiente: s.nombre, nivel: n.id, padre: r.id, grupo_1633: r.grupo_1633, servicio_programa: r.servicio_programa });
  }
  // exigencias de la matriz (por id) y nombre de cada servicio de la matriz
  const exig = new Map(), nombreSrvHab = new Map();
  for (const e of habilitacion?.todos_los_servicios?.detalle || []) exig.set(e.id, { ...e, servicio: null, servicio_nombre: 'Todos los servicios' });
  for (const s of habilitacion?.servicios || []) { nombreSrvHab.set(s.id, s.nombre); for (const e of s.exigencias || []) exig.set(e.id, { ...e, servicio: s.id, servicio_nombre: s.nombre }); }
  const nombreServicio = (id) => SERVICIOS[id] || nombreSrvHab.get(id) || palabras(id);

  const U = filas.map((f, i) => {
    const x = extra[String(i)] || {}, l = lineas[f[col.linea_idx]] || {};
    const comp = f[col.componente_de_idx];
    const u = {
      i, id: f[col.id], li: f[col.linea_idx], linea: l, nivel: nivelDe(i), piso: f[col.piso], recinto: f[col.recinto] ?? null, sub: x.sub ?? null,
      x: +f[col.x] || 0, y: +f[col.y] || 0, z: +f[col.z] || 0, rot: +f[col.rot_z] || 0,
      apoyo: f[col.apoyo_idx] ?? -1, dentro: f[col.dentro_de_idx] ?? -1, componente: comp ?? -1, montaje: f[col.montaje], estado: f[col.estado], extra: x,
      nombre: x.n || l.nombre || f[col.id], modelo: x.m3d || l.modelo3d || null, capa: l.capa || null,
      clase: x.clase || l.clase || null, registro: x.registro || l.registro || null,
    };
    // valor: precio unitario de la línea; los componentes de un kit van en 0 (ya están en el precio del kit)
    u.valor = comp != null && comp >= 0 ? 0 : (+l.precio || 0);
    return u;
  });
  // unidades de zona sin recinto en los datos (pérgola, filas de la terraza, barandas, ambulancias): su recinto es el que
  // contiene su posición en la planta de su nivel
  const recsNivel = new Map((plantas?.niveles || []).map((n) => [n.id, n.recintos || []]));
  for (const u of U) {
    if (u.recinto || !u.extra.recinto_por_posicion) continue;
    const r = (recsNivel.get(u.nivel) || []).find((q) => q.transitable !== false && dentroPol(u.x, u.y, q.poligono)) || (recsNivel.get(u.nivel) || []).find((q) => dentroPol(u.x, u.y, q.poligono));
    if (r) u.recinto = r.id;
  }
  const porId = new Map(U.map((u) => [String(u.id), u]));
  const porRecinto = new Map();
  for (const u of U) { if (!u.recinto) continue; if (!porRecinto.has(u.recinto)) porRecinto.set(u.recinto, []); porRecinto.get(u.recinto).push(u); }
  const hijosDentro = new Map(), hijosComp = new Map();
  for (const u of U) {
    if (u.dentro >= 0) { if (!hijosDentro.has(u.dentro)) hijosDentro.set(u.dentro, []); hijosDentro.get(u.dentro).push(u); }
    if (u.componente >= 0) { if (!hijosComp.has(u.componente)) hijosComp.set(u.componente, []); hijosComp.get(u.componente).push(u); }
  }
  const implementos = inv?.implementos || {};
  const plantillaDe = (u) => u.extra.plantilla || u.linea.plantilla || null;
  const itemsDe = (u) => { const p = plantillaDe(u); return p ? (Array.isArray(p) ? p : implementos[p] || []) : []; };
  // texto de búsqueda de cada unidad (sin tildes): lo suyo y, aparte, sus implementos internos (reactivos de un analizador,
  // contenido de un carro de paro…), para que «lisante» o «adrenalina» lleven al equipo que los guarda (16.2 y 16.4)
  const textoItem = (it) => normal(`${it.n || ''} ${it.pres || ''}`);
  for (const u of U) {
    u.busca = normal(`${u.nombre} ${u.linea.especificacion || ''} ${recintos.get(u.recinto)?.ambiente || ''} ${nombreServicio(u.linea.servicio)} ${u.extra.ubic || ''} ${u.id}`);
    u.buscaItems = itemsDe(u).map(textoItem).join(' | ');
  }
  // implementos internos de u que coinciden con todas las palabras buscadas (para «contiene: …» en el buscador)
  const contiene = (u, texto) => {
    const q = normal(texto).trim().split(/\s+/).filter(Boolean);
    if (!q.length || !u.buscaItems || q.every((p) => u.busca.includes(p))) return [];
    return itemsDe(u).filter((it) => { const t = textoItem(it); return q.every((p) => t.includes(p)); });
  };
  // valor de una unidad para los totales: dotación, fijo y cierre de brechas (el laboratorio en comodato no suma)
  const sumaValor = (u) => (['dotacion', 'fijo', 'cierre_brechas'].includes(u.capa) ? u.valor : 0);

  // ---- textos de apoyo
  const nombreRecinto = (id) => { const r = recintos.get(id); return r ? limpio(r.ambiente || r.nombre || id) : id ? String(id) : ''; };
  const lugar = (u) => {
    const r = u.recinto ? nombreRecinto(u.recinto) : limpio(u.extra.ubic || 'sin recinto');
    const s = u.sub && recintos.get(u.sub) ? ` · ${limpio(recintos.get(u.sub).ambiente)}` : '';
    return `${r}${s}`;
  };
  const clase = (c) => (c?.vigente ? CLASES[c.vigente] || c.vigente : '—');
  const pill = (txt, cls = '') => `<span class="pill ${cls}">${esc(txt)}</span>`;
  const exigibleTxt = (e) => (e === 'si' ? 'exigido (texto oficial)' : e === 'por_confirmar' ? 'según guía secundaria; por confirmar' : e === 'no' ? 'no exigible' : palabras(e));
  const enlace = (url, txt = 'fuente') => (/^https?:\/\//.test(String(url || '')) ? ` <a href="${escH(url)}" target="_blank" rel="noopener">${esc(txt)}</a>` : '');
  const fuenteTexto = (s) => { const m = String(s || '').match(/https?:\/\/\S+/); return `${esc(String(s || '').replace(/:?\s*https?:\/\/\S+/, ''))}${m ? enlace(m[0]) : ''}`; };

  function exigenciaHTML(ref) {
    const e = exig.get(ref.id);
    const verif = e ? nivelVerificacion(e.verificacion_texto || '') : '';
    const texto = e ? (e.texto_disponible ? `«${esc(e.texto_corto || e.que_exige || '')}»` : `${esc(e.que_exige || e.texto_corto || '')} <small class="note">(resumen; texto oficial no obtenido)</small>`) : '';
    return `<li><b>${esc(e?.numeral ? `Res. 3100, num. ${String(e.numeral).replace(/^Manual, num\. /, '')}` : ref.id)}</b> · ${esc(exigibleTxt(ref.exigible))}${texto ? `<br>${texto}` : ''}${verif ? `<br><small class="note">${esc(verif)}${e?.fuente_url ? enlace(e.fuente_url) : ''}</small>` : ''}</li>`;
  }
  function implementosHTML(items, { titulo = 'Implementos internos' } = {}) {
    if (!items?.length) return '';
    const grupos = new Map();
    for (const it of items) { const k = it.comp || 'sin compartimiento'; if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(it); }
    return `<details class="fold reco-impl"><summary>${esc(titulo)} (${items.length})</summary>${[...grupos].map(([k, L]) => `<h5>${esc(palabras(k))}</h5><ul class="tight">${L.map((it) => `<li>${it.c ? `${fmtN(it.c)} × ` : ''}${esc(it.n)}${it.pres ? ` <small class="note">(${esc(it.pres)})</small>` : ''}${it.clase ? ` ${pill(`clase ${CLASES[it.clase] || it.clase}`)}` : ''}${it.reg ? ` <small class="note">registro INVIMA: ${esc(palabras(it.reg))}</small>` : ''}
        ${it.alm ? `<br><small class="note">Se guarda: ${esc(it.alm.cond || '')}${it.alm.donde_n ? ` · ${esc(it.alm.donde_n)}` : ''}</small>` : ''}
        ${it.pruebas?.length ? `<br><small class="note">Pruebas: ${esc(it.pruebas.join(', '))}${it.pm ? ` · ${fmtN(it.pm)} al mes` : ''}${it.metodo ? ` · ${esc(it.metodo)}` : ''}</small>` : ''}
        ${it.regimen ? `<br><small class="note">${esc(it.regimen)}</small>` : ''}
        ${it.verif || it.td ? `<br><small class="note">${esc(nivelVerificacion(it.td || it.verif))}</small>` : ''}</li>`).join('')}</ul>`).join('')}</details>`;
  }
  function sismoHTML(u) {
    const c = inv?.catalogo?.[u.modelo];
    if (!c) return '';
    const anc = ANCLAJE[c.anc] || palabras(c.anc);
    const nota = c.anc === 'apoyado' || c.anc === 'ruedas_con_freno' ? 'puede deslizarse o volcarse en un sismo fuerte: conviene anclarlo o frenarlo (estimación)' : c.anc === 'anclado' ? 'anclado: se mueve con el edificio' : '';
    return `<dt>Riesgo en un sismo</dt><dd>${esc(anc)}${c.masa ? ` · ${fmtN(c.masa)} kg` : ''}${nota ? `<br><small class="note">${esc(nota)}</small>` : ''}</dd>`;
  }

  // ---- ficha de una unidad (16.4)
  function fichaUnidad(id) {
    const u = porId.get(String(id));
    if (!u) return '';
    const l = u.linea, cl = u.clase || {}, rg = u.registro || {}, mt = u.extra.mant || l.mantenimiento || {};
    const madre = u.componente >= 0 ? U[u.componente] : null, contenedor = u.dentro >= 0 ? U[u.dentro] : null;
    const prev = inv?.mantenimiento_preventivo || {};
    const preventivo = ['infraestructura', 'contexto'].includes(u.capa) ? prev.edificacion : l.adquisicion === 'comodato' ? prev.comodato : prev.fabricante;
    const exs = (u.extra.exig || l.exigencias || []);
    const precio = u.capa === 'infraestructura' || u.capa === 'contexto'
      ? `<dt>Precio</dt><dd>Sin precio de dotación: es obra${(l.cita_presupuesto || []).length ? ` (presupuesto de obra, ítem ${esc(l.cita_presupuesto.map((c) => c.item).join(', '))})` : ''}</dd>`
      : `<dt>Precio unitario</dt><dd>${l.precio ? fmtCOP(l.precio) : 'por cotizar'}${u.valor === 0 && madre ? '<br><small class="note">incluido en el precio del kit</small>' : ''}${l.rango ? `<br><small class="note">rango ${fmtCOP(l.rango[0])} a ${fmtCOP(l.rango[1])}</small>` : ''}</dd>
        <dt>Tipo de precio</dt><dd>${esc(TIPO_PRECIO[l.tipo_precio] || palabras(l.tipo_precio || '—'))}</dd>`;
    const hijos = (hijosComp.get(u.i) || []), dentro = (hijosDentro.get(u.i) || []).filter((h) => !hijos.includes(h));
    const lista = (L, t) => (L.length ? `<details class="fold" open><summary>${esc(t)} (${L.length})</summary><ul class="tight">${L.map((h) => `<li><button type="button" class="reco-link" data-unidad="${escH(h.id)}">${esc(h.nombre)}</button>${h.clase?.vigente ? ` ${pill(`clase ${clase(h.clase)}`)}` : ''}${h.registro?.requerido ? ` <small class="note">registro INVIMA ${esc(h.registro.requerido === 'si' ? 'requerido' : palabras(h.registro.requerido))}</small>` : ''}</li>`).join('')}</ul></details>` : '');
    return `<h4>${esc(u.nombre)}</h4>
      <p>${pill(CAPAS[u.capa] || palabras(u.capa))} ${pill(ESTADOS_U[u.estado] || palabras(u.estado), u.estado === 'cierre_brechas_propuesto' ? 'p1' : '')}</p>
      ${l.especificacion ? `<p class="note">${esc(l.especificacion)}</p>` : ''}
      <dl class="kv reco-kv">
        <dt>Servicio</dt><dd>${esc(nombreServicio(l.servicio))}</dd>
        <dt>Dónde</dt><dd>${esc(lugar(u))}<br><small class="note">${esc(NOMBRE_NIVEL[u.nivel] || u.nivel || '')} · ${esc(MONTAJE[u.montaje] || palabras(u.montaje || ''))}${contenedor ? ` de ${esc(contenedor.nombre)}` : ''}</small></dd>
        <dt>Cantidad en la línea</dt><dd>${fmtN(l.cantidad || 1)}</dd>
        ${madre ? `<dt>Parte de</dt><dd><button type="button" class="reco-link" data-unidad="${escH(madre.id)}">${esc(madre.nombre)}</button></dd>` : ''}
        <dt>Clase de riesgo</dt><dd>${esc(clase(cl))}${cl.estado && cl.estado !== 'coherente' ? `<br><small class="note">${esc(palabras(cl.estado))}${cl.revision?.valor ? `: revisión ${esc(CLASES[cl.revision.valor] || cl.revision.valor)}` : ''}</small>` : ''}${cl.regla || cl.revision?.regla ? `<br><small class="note">${esc(cl.regla || cl.revision.regla)}</small>` : ''}</dd>
        <dt>Registro INVIMA</dt><dd>${esc(rg.requerido === 'si' ? 'requerido' : rg.requerido === 'no' ? 'no requerido' : palabras(rg.requerido || '—'))}${rg.via ? `<br><small class="note">${esc(via(rg.via))}</small>` : ''}${rg.usado_permitido === false ? '<br><small class="note">no se puede comprar ni recibir usado</small>' : ''}${rg.nota ? `<br><small class="note">${esc(rg.nota)}</small>` : ''}</dd>
        <dt>Prioridad</dt><dd>${esc(PRIORIDAD[l.prioridad] || palabras(l.prioridad || '—'))}${l.prioridad_revisada ? `<br><small class="note">revisada: ${esc(PRIORIDAD[l.prioridad_revisada] || palabras(l.prioridad_revisada))}${l.norma_base ? ` (${esc(l.norma_base)})` : ''}</small>` : ''}</dd>
        <dt>Mantenimiento</dt><dd>${mt.anual_pct != null ? `${fmtN(mt.anual_pct, 1)} % al año` : '—'}${mt.vida_util_anios ? ` · vida útil ${fmtN(mt.vida_util_anios)} años` : ''}${mt.personal_inscrito_invima ? '<br><small class="note">por personal inscrito en el INVIMA</small>' : ''}${mt.calibracion ? '<br><small class="note">con calibración</small>' : ''}${preventivo ? `<br><small class="note">${esc(preventivo)}</small>` : ''}</dd>
        ${precio}
        ${l.nota_precio ? `<dt>Nota</dt><dd><small>${esc(l.nota_precio)}</small></dd>` : ''}
        ${sismoHTML(u)}
      </dl>
      <h5>Lo que pide la norma</h5>
      ${exs.length ? `<ul class="tight reco-exig">${exs.map(exigenciaHTML).join('')}</ul>` : `<p class="note">${esc(l.nota_exigencias || (l.prioridad === 'recomendado' ? 'Recomendado: no lo exige un numeral de la Res. 3100.' : 'Sin exigencia normativa asociada.'))}</p>`}
      ${l.justificacion_recomendado ? `<p class="note">${esc(l.justificacion_recomendado)}</p>` : ''}
      ${lista(hijos, 'Equipos que lo componen')}
      ${lista(dentro, 'Contenido')}
      ${implementosHTML(itemsDe(u))}
      ${(l.fuentes_precio || []).length ? `<details class="fold"><summary>De dónde sale el precio (${l.fuentes_precio.length})</summary><ul class="tight">${l.fuentes_precio.map((f) => `<li><small>${fuenteTexto(f)}</small></li>`).join('')}</ul>${l.metodo_precio ? `<p class="note">${esc(l.metodo_precio)}</p>` : ''}</details>` : ''}
      ${['dotacion', 'fijo', 'laboratorio', 'cierre_brechas'].includes(u.capa) && (inv?.campos_al_comprar || []).length ? `<details class="fold"><summary>Lo que se anota al comprarlo</summary><p class="note">${esc(inv.campos_al_comprar.join(' · '))}</p></details>` : ''}
      <p class="note">Textos normativos tomados de compilaciones oficiales vistas por buscador o de guías secundarias: cotejar con el Diario Oficial antes de radicar.</p>`;
  }
  // ficha de un implemento visible (cajas de reactivos y frascos en neveras y estantes del laboratorio)
  function fichaImplemento(uid, k) {
    const u = porId.get(String(uid)), it = u && itemsDe(u)[k];
    if (!it) return '';
    return `<h4>${esc(it.n)}</h4><p>${pill('Implemento interno')} ${it.td || it.verif ? pill(nivelVerificacion(it.td || it.verif)) : ''}</p>
      <dl class="kv reco-kv">
        <dt>De</dt><dd><button type="button" class="reco-link" data-unidad="${escH(u.id)}">${esc(u.nombre)}</button></dd>
        ${it.c ? `<dt>Cantidad</dt><dd>${fmtN(it.c)}</dd>` : ''}
        ${it.pres ? `<dt>Presentación</dt><dd>${esc(it.pres)}</dd>` : ''}
        ${it.alm ? `<dt>Se guarda</dt><dd>${esc(it.alm.cond || '')}${it.alm.donde_n ? `<br><small class="note">${esc(it.alm.donde_n)}</small>` : ''}</dd>` : ''}
        ${it.pruebas?.length ? `<dt>Pruebas</dt><dd>${esc(it.pruebas.join(', '))}${it.pm ? `<br><small class="note">${fmtN(it.pm)} al mes</small>` : ''}</dd>` : ''}
        ${it.metodo ? `<dt>Método</dt><dd>${esc(it.metodo)}</dd>` : ''}
        ${it.regimen ? `<dt>Régimen</dt><dd><small>${esc(it.regimen)}</small></dd>` : ''}
      </dl>${it.fuente ? `<p class="note">${esc(it.fuente)}</p>` : ''}`;
  }
  // estado de cumplimiento de un recinto (matriz por recinto)
  const estadoRecinto = (id, corte = 'corte_2026') => (habilitacion?.por_recinto?.[id] || inv?.recintos?.[id])?.estado?.[corte] || null;
  function fichaRecinto(id) {
    const r = recintos.get(id);
    if (!r) return '';
    const pr = habilitacion?.por_recinto?.[r.padre || id] || inv?.recintos?.[r.padre || id];
    const ex = pr?.exigencias || pr?.exig || [];
    return `<h4>${esc(r.ambiente || r.nombre || id)}</h4>
      <dl class="kv reco-kv">
        <dt>Nivel</dt><dd>${esc(NOMBRE_NIVEL[r.nivel] || r.nivel)}</dd>
        ${r.servicio_programa ? `<dt>Servicio</dt><dd>${esc(r.servicio_programa)}</dd>` : ''}
        ${r.area_ejes_m2 ? `<dt>Área a ejes · libre</dt><dd>${fmtN(r.area_ejes_m2, 1)} · ${fmtN(r.area_libre_m2 || 0, 1)} m²</dd>` : ''}
        ${r.minimo_1633?.m2 ? `<dt>Mínimo de la Res. 1633</dt><dd>${fmtN(r.minimo_1633.m2, 1)} m²</dd>` : ''}
        ${r.climatizacion?.presion ? `<dt>Climatización</dt><dd>presión ${esc(r.climatizacion.presion === '+' ? 'positiva' : r.climatizacion.presion === '-' ? 'negativa' : r.climatizacion.presion)}${r.climatizacion.cambios_h ? ` · ${fmtN(r.climatizacion.cambios_h)} cambios por hora` : ''}</dd>` : ''}
        ${pr ? `<dt>Cumplimiento en dotación e infraestructura</dt><dd>${esc(ESTADOS_R[pr.estado?.corte_2026] || '—')} (hoy) · ${esc(ESTADOS_R[pr.estado?.apertura] || '—')} (apertura)<br><small class="note">${fmtN(ex.length - (pr.por_confirmar || 0))} exigibles${pr.por_confirmar ? ` y ${fmtN(pr.por_confirmar)} por confirmar` : ''}</small></dd>` : ''}
      </dl>
      ${(r.notas || []).length ? `<p class="note">${esc(r.notas.join(' '))}</p>` : ''}
      ${ex.length ? `<details class="fold"><summary>Exigencias que aplican aquí (${ex.length})</summary><ul class="tight reco-exig">${ex.map((x) => exigenciaHTML({ id: x, exigible: exig.get(x)?.exigible })).join('')}</ul></details>` : ''}`;
  }
  // lista de dotación de un recinto, agrupada por línea (cada fila es un botón que resalta y abre la ficha)
  function listaRecinto(id) {
    const L = (porRecinto.get(id) || []).filter((u) => u.montaje !== 'dentro' && u.componente < 0);
    if (!L.length) return '<p class="note">Sin dotación ni infraestructura ubicada en este recinto.</p>';
    const grupos = new Map();
    for (const u of L) { const k = `${u.li}|${u.estado}`; if (!grupos.has(k)) grupos.set(k, []); grupos.get(k).push(u); }
    const orden = { dotacion: 0, laboratorio: 1, fijo: 2, cierre_brechas: 3, infraestructura: 4, contexto: 5 };
    const filasG = [...grupos.values()].sort((a, b) => (orden[a[0].capa] ?? 9) - (orden[b[0].capa] ?? 9) || a[0].nombre.localeCompare(b[0].nombre, 'es'));
    return `<ul class="reco-lista">${filasG.map((G) => {
      const u = G[0], l = u.linea, exs = l.exigencias || [];
      const etiqueta = u.estado === 'cierre_brechas_propuesto' ? 'faltante (cierre propuesto)' : u.capa === 'infraestructura' ? 'infraestructura' : u.capa === 'contexto' ? 'contexto' : u.capa === 'laboratorio' ? palabras(l.adquisicion || 'laboratorio') : exs.some((e) => e.exigible === 'si') ? 'exigido (texto oficial)' : exs.length ? 'según guía secundaria; por confirmar' : l.prioridad === 'recomendado' ? 'recomendado' : '';
      const cls = u.estado === 'cierre_brechas_propuesto' ? 'p1' : '';
      return `<li><button type="button" data-unidad="${escH(u.id)}" data-unidades="${escH(G.map((g) => g.id).join(' '))}"><span class="reco-n">${fmtN(G.length)} ×</span> <span class="reco-t">${esc(u.nombre)}</span>${u.clase?.vigente && !['no_dm'].includes(u.clase.vigente) ? ` ${pill(`clase ${clase(u.clase)}`)}` : ''}${etiqueta ? ` ${pill(etiqueta, cls)}` : ''}</button></li>`;
    }).join('')}</ul>`;
  }

  // ---- búsqueda con filtros (16.4)
  function buscar({ texto = '', nivel = '', servicio = '', recinto = '', capa = '', clase: cl = '', estado = '' } = {}) {
    const q = normal(texto).trim().split(/\s+/).filter(Boolean);
    const out = [];
    let valor = 0, comodato = 0;
    for (const u of U) {
      if (u.nivel === 'fuera_de_la_torre') continue;
      if (nivel && u.nivel !== nivel) continue;
      if (servicio && u.linea.servicio !== servicio) continue;
      if (recinto && u.recinto !== recinto) continue;
      if (capa && u.capa !== capa) continue;
      if (cl && (u.clase?.vigente || '') !== cl) continue;
      if (estado) {
        if (estado.startsWith('u:') && u.estado !== estado.slice(2)) continue;
        if (estado.startsWith('r:') && estadoRecinto(u.recinto) !== estado.slice(2)) continue;
      }
      if (q.length && !q.every((p) => u.busca.includes(p)) && !(u.buscaItems && itemsDe(u).some((it) => { const t = textoItem(it); return q.every((p) => t.includes(p)); }))) continue;
      out.push(u);
      valor += sumaValor(u);
      if (u.capa === 'laboratorio' && u.componente < 0) comodato += +u.linea.precio || 0;
    }
    // con texto, primero lo que coincide en el nombre, después en la especificación o el recinto y al final en los
    // implementos internos
    if (q.length) {
      const orden = (u) => (u._nom ??= normal(u.nombre), q.every((p) => u._nom.includes(p)) ? 0 : q.every((p) => u.busca.includes(p)) ? 1 : 2);
      out.sort((a, b) => orden(a) - orden(b));
    }
    return { unidades: out, valor, comodato };
  }
  const opciones = () => {
    const srv = [...new Set(U.map((u) => u.linea.servicio).filter(Boolean))].sort((a, b) => nombreServicio(a).localeCompare(nombreServicio(b), 'es'));
    const clases = [...new Set(U.map((u) => u.clase?.vigente).filter(Boolean))];
    return { servicios: srv.map((s) => [s, nombreServicio(s)]), clases: clases.map((c) => [c, CLASES[c] || c]) };
  };
  return {
    unidades: U, porId, porRecinto, recintos, exig, implementos, lineas,
    unidad: (id) => porId.get(String(id)) || null,
    itemsDe, contiene, nombreServicio, nombreRecinto, lugar, estadoRecinto,
    fichaUnidad, fichaImplemento, fichaRecinto, listaRecinto, buscar, opciones,
    total: U.length,
  };
}

// ---------------------------------------------------------------- buscador (panel del recorrido)
// op: { irA(idUnidad, { implementos }), textos }. Devuelve { refrescar(), filtrar(valores), resultados() }.
export function montarBuscador(el, modelo, { irA, textos }) {
  const { esc, escH } = textos;
  const op = modelo.opciones();
  const POR_PAGINA = 40;
  el.innerHTML = `<div class="reco-busca ctl">
      <label>Buscar en el inventario <input type="search" data-f="texto" placeholder="Nombre, recinto, servicio o reactivo" autocomplete="off"></label>
      <div class="reco-filtros">
        <label>Nivel <select data-f="nivel"><option value="">Todos</option>${NIVELES.map((n) => `<option value="${n}">${esc(NOMBRE_NIVEL[n])}</option>`).join('')}</select></label>
        <label>Servicio <select data-f="servicio"><option value="">Todos</option>${op.servicios.map(([v, t]) => `<option value="${escH(v)}">${esc(t)}</option>`).join('')}</select></label>
        <label>Recinto <select data-f="recinto"><option value="">Todos</option></select></label>
        <label>Capa <select data-f="capa"><option value="">Todas</option>${Object.entries(CAPAS).map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('')}</select></label>
        <label>Clase de riesgo <select data-f="clase"><option value="">Todas</option>${op.clases.map(([v, t]) => `<option value="${escH(v)}">${esc(t)}</option>`).join('')}</select></label>
        <label>Estado <select data-f="estado"><option value="">Todos</option><optgroup label="De la unidad">${Object.entries(ESTADOS_U).filter(([k]) => k !== 'fuera_de_la_torre').map(([v, t]) => `<option value="u:${v}">${esc(t)}</option>`).join('')}</optgroup><optgroup label="Cumplimiento del recinto (hoy)">${Object.entries(ESTADOS_R).filter(([k]) => k !== 'no_aplica').map(([v, t]) => `<option value="r:${v}">${esc(t)}</option>`).join('')}</optgroup></select></label>
      </div>
      <p class="reco-totales" aria-live="polite"></p>
      <ul class="reco-res"></ul>
      <button type="button" class="btn ghost reco-mas" hidden>Mostrar más</button>
    </div>`;
  const f = (k) => el.querySelector(`[data-f="${k}"]`);
  const tot = el.querySelector('.reco-totales'), res = el.querySelector('.reco-res'), mas = el.querySelector('.reco-mas');
  let lista = [], n = 0;
  const llenarRecintos = () => {
    const nivel = f('nivel').value, sel = f('recinto'), previo = sel.value;
    const ids = [...modelo.porRecinto.keys()].filter((id) => !nivel || modelo.recintos.get(id)?.nivel === nivel)
      .sort((a, b) => modelo.nombreRecinto(a).localeCompare(modelo.nombreRecinto(b), 'es'));
    sel.innerHTML = `<option value="">Todos</option>${ids.map((id) => `<option value="${escH(id)}">${esc(modelo.nombreRecinto(id))}${nivel ? '' : ` (${esc(NOMBRE_NIVEL[modelo.recintos.get(id)?.nivel] || '')})`}</option>`).join('')}`;
    if (ids.includes(previo)) sel.value = previo;
  };
  const fila = (u) => {
    // si coincide por lo que guarda adentro, se dice qué (y «Ir a» abre su ficha con los implementos desplegados)
    const c = modelo.contiene(u, f('texto').value);
    const cont = c.length ? `<br><small class="reco-contiene">contiene: ${esc(c[0].n)}${c[0].pres ? ` (${esc(c[0].pres)})` : ''}${c.length > 1 ? ` y ${fmtN(c.length - 1)} más` : ''}</small>` : '';
    return `<li><span class="reco-r-n"><b>${esc(u.nombre)}</b>${cont}<br><small class="note">${esc(modelo.lugar(u))} · ${esc(NOMBRE_NIVEL[u.nivel] || '')}${u.valor && ['dotacion', 'fijo', 'cierre_brechas'].includes(u.capa) ? ` · ${fmtCOP(u.valor)}` : ''}</small></span>
      <span class="reco-r-b"><button type="button" class="reco-ir" data-ir="${escH(u.id)}"${c.length ? ' data-impl="1"' : ''} aria-label="Ir a ${escH(u.nombre)} en ${escH(modelo.lugar(u))}${c.length ? `, que contiene ${escH(c[0].n)}` : ''}">Ir a</button></span></li>`;
  };
  const pintar = () => {
    res.innerHTML = lista.slice(0, n).map(fila).join('');
    mas.hidden = n >= lista.length;
    mas.textContent = `Mostrar más (${fmtN(lista.length - n)} restantes)`;
  };
  function refrescar() {
    const r = modelo.buscar({ texto: f('texto').value, nivel: f('nivel').value, servicio: f('servicio').value, recinto: f('recinto').value, capa: f('capa').value, clase: f('clase').value, estado: f('estado').value });
    lista = r.unidades; n = Math.min(POR_PAGINA, lista.length);
    tot.innerHTML = `<b>${fmtN(lista.length)}</b> unidades · <b>${fmtCOP(r.valor)}</b> en dotación, equipamiento fijo y cierre de brechas${r.comodato ? ` <small class="note">(más ${fmtCOP(r.comodato)} de valor de mercado del laboratorio en comodato, que no suma)</small>` : ''}`;
    pintar();
  }
  let tEscribir = 0;
  el.addEventListener('input', (ev) => { if (ev.target.dataset.f === 'texto') { clearTimeout(tEscribir); tEscribir = setTimeout(refrescar, 140); } });
  el.addEventListener('change', (ev) => { if (ev.target.dataset.f === 'nivel') llenarRecintos(); if (ev.target.dataset.f && ev.target.dataset.f !== 'texto') refrescar(); });
  el.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-ir]');
    if (b) { irA(b.dataset.ir, { implementos: !!b.dataset.impl }); return; }
    if (ev.target === mas) { n = Math.min(lista.length, n + POR_PAGINA); pintar(); }
  });
  llenarRecintos();
  refrescar();
  return {
    refrescar,
    // fija los filtros (para QA y para «ver lo de este recinto»)
    filtrar(valores = {}) { for (const [k, v] of Object.entries(valores)) { const s = f(k); if (s) s.value = v; if (k === 'nivel') llenarRecintos(); } refrescar(); },
    resultados: () => lista,
  };
}
