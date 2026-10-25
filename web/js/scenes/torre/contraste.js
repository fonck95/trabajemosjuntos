// Contraste de la torre con el proyecto tipo (equipo E; especificación de integración, 9.2).
// Datos: data/torre_contraste.json, que escribe scripts/build_data.py desde data/proyectos/torre_hospital/
// proyecto_tipo_contraste.json (y calcula el costo de la torre de cada fila de dotación con los precios de dotacion.json).
// torre.js lo carga de forma perezosa y usa sus tres funciones:
//   pintarContraste(el, c, { verEn3D, textos })  tarjeta [data-slot="torre.tipo"]: solo escribe en `el`
//   coloresRecintos(c, plantas)                  Map<idRecinto, { veredicto_tipo, color_hex, texto }> para la capa del recorrido
//   modeloTipo3D(THREE, c)                       placa de 320,6 m² (un piso) centrada en el origen, con su etiqueta
// No importa three ni core.js (THREE llega como argumento). Todo texto de los datos pasa por textos.js (limpio y esc).
import * as TEXTOS from './textos.js';

const VEREDICTOS = ['mejora', 'cumple igual', 'se aparta', 'falta'];
const PLURAL = { mejora: 'mejoran', 'cumple igual': 'igual', 'se aparta': 'se apartan', falta: 'faltan' };
const PLURAL_NORMA = { mejora: 'sobre el mínimo', 'cumple igual': 'en el mínimo', 'se aparta': 'se apartan', falta: 'por debajo o por confirmar' };
// con un solo ambiente el verbo va en singular («1 falta», no «1 faltan»)
const SINGULAR = { faltan: 'falta', mejoran: 'mejora', 'se apartan': 'se aparta' };
const cuenta = (n, txt) => `${n} ${n === 1 ? SINGULAR[txt] || txt : txt}`;
const ESTADO_PAR = { cubre: 'cubre', 'cubre en parte': 'cubre en parte', compartido: 'compartido', falta: 'falta', 'se aparta': 'se aparta', sobra: 'sobra en la torre' };
// colores fijos solo para el 3D (la tarjeta usa los tokens del tema: --good, --s1, --warn, --bad con texto --ink)
const COLORES_3D = { mejora: '#2f6b4f', 'cumple igual': '#6b8fb3', 'se aparta': '#c9a227', falta: '#b5562f' };
const BASE_CORTA = {
  torre_construida: 'torre construida', torre_util: 'área útil de la torre', proyecto_construido: 'proyecto construido',
  tipo_texto: 'puesto tipo, construido', tipo_presupuesto: 'puesto tipo, presupuesto', modulo_dnp: 'módulo DNP',
};

const num = (v) => typeof v === 'number' && Number.isFinite(v);
const fmt = (v, d = 2) => (num(v) ? v.toLocaleString('es-CO', { maximumFractionDigits: d }) : '—');
const fmtF = (v, d = 1) => (num(v) ? v.toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—');
const pesos = (v) => (num(v) ? `$${Math.round(v).toLocaleString('es-CO')}` : '—');
const pesosM = (v) => {
  if (!num(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toLocaleString('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} mil M`;
  if (a >= 1e6) return `$${(v / 1e6).toLocaleString('es-CO', { maximumFractionDigits: a < 1e8 ? 1 : 0 })} M`;
  return pesos(v);
};
// piso del recorrido a partir del id del recinto (1.3): P2-A066-01 → 2; BT-…, EXT-…, CUB-… → su nivel
const pisoDe = (id) => { const m = /^P(\d)-/.exec(id || ''); return m ? +m[1] : String(id || '').split('-')[0] || null; };

// ---------------------------------------------------------------------------------------------------------------------
// Tarjeta «Contraste con el proyecto tipo»
// ---------------------------------------------------------------------------------------------------------------------
export function pintarContraste(el, c, { verEn3D, textos } = {}) {
  if (!el) return;
  const T = { ...TEXTOS, ...(textos || {}) };
  const escH = T.escH;
  // además de limpio(): quita las referencias a claves internas que traen los textos de la investigación
  // («(ver dotacion_por_ambiente)», «Ver costo_m2.», «(materiales_y_volumetria)»)
  const sinClaves = (s) => String(s).replace(/\s*\((?:ver\s+)?[a-z]+(?:_[a-z0-9]+)+\)/gi, '').replace(/\s*Ver\s+[a-z]+(?:_[a-z0-9]+)+\.?/g, '');
  const esc = (s) => escH(sinClaves(T.limpio(s ?? '')));
  if (!c) { el.innerHTML = '<p class="note">El contraste con el proyecto tipo todavía no está publicado.</p>'; return; }
  const pill = (v, txt) => (v ? `<span class="tc-v" data-v="${escH(v)}">${esc(txt ?? v)}</span>` : '<span class="tc-v" data-v="sin">sin veredicto</span>');
  const boton = (id, que) => (verEn3D && id ? `<button type="button" class="tc-3d" data-ver3d="${escH(id)}" aria-label="Ver en 3D: ${escH(T.limpio(que))}">Ver en 3D</button>` : '');
  const m2 = (v) => (num(v) ? `${fmt(v)} m²` : v == null ? '—' : esc(v));
  const ref = Object.fromEntries((c.referentes || []).map((r) => [r.id, r]));
  const bases = c.resumen_para_la_web?.bases_de_area || {};
  const nombres = { ...(c.nombres_lineas || {}) };
  (c.dotacion_por_ambiente || []).forEach((f) => (f.lineas_torre || []).forEach((l) => { if (l.nombre) nombres[l.linea] = l.nombre; }));
  const nombreLinea = (id) => esc(nombres[id] || 'ítem de la dotación');

  // 1. referente principal y por tema
  const rp = c.referente_principal || {};
  const principal = ref[rp.proyecto_tipo_oficial_mas_cercano];
  // los referentes se citan por su id («minproteccion_guia_pma_hospital_tipo_2010 + res_1633_2025_anexo_1»): se nombran
  const idsRef = Object.keys(ref).sort((a, b) => b.length - a.length).map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const reRef = idsRef.length ? new RegExp(`(${idsRef.join('|')})`, 'g') : null;
  const refTexto = (s) => (reRef ? String(s || '').replace(/ \+ /g, ' y ').split(reRef).map((p, i) => (i % 2 ? esc(ref[p].nombre) : esc(p))).join('') : esc(s));
  const hRef = `<p>${esc(rp.respuesta)}</p>
    ${principal ? `<p class="note">Referente principal: ${principal.url ? `<a href="${escH(principal.url)}" target="_blank" rel="noopener">${esc(principal.nombre)}</a>` : esc(principal.nombre)} (${esc(principal.fecha)}).</p>` : ''}
    <details class="fold"><summary>Referente por tema</summary><div class="tbl-wrap"><table class="fichas"><thead><tr><th>Tema</th><th>Referente</th></tr></thead><tbody>
    ${(rp.referente_por_tema || []).map((x) => `<tr><td>${esc(x.tema)}</td><td data-th="Referente" class="ancho">${refTexto(x.referente)}</td></tr>`).join('')}
    </tbody></table></div>
    ${(rp.por_que_no_hay_uno_mas_cercano || []).length ? `<p class="tc-sub"><b>Por qué no hay uno más cercano</b></p><ul class="tc-lista">${rp.por_que_no_hay_uno_mas_cercano.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</details>`;

  // 2. cifras del resumen, cada una con su tipo de dato y su base de área
  const valorCifra = (x) => {
    const v = x.valor;
    if (x.id === 'ambientes_tipo' || x.id === 'ambientes_norma') {
      const pl = x.id === 'ambientes_tipo' ? PLURAL : PLURAL_NORMA;
      return `<span class="tc-cuentas">${VEREDICTOS.map((k) => pill(k, cuenta(v?.[k] ?? 0, pl[k]))).join(' ')}</span>`;
    }
    if (x.id === 'costo_obra_civil' && Array.isArray(v)) return `<b>+${fmtF(v[0])} % a +${fmtF(v[1])} %</b>`;
    if (x.id === 'dotacion' && Array.isArray(v)) return `<b>${fmtF(v[0])} veces</b><span class="tc-sub">${fmtF(v[1])} veces por m²</span>`;
    if (Array.isArray(v)) return `<b>${fmt(v[0])} a ${fmt(v[1])} ${esc(x.unidad || '')}</b>`;
    if (num(v)) return `<b>${fmt(v, 1)}${x.unidad === '%' ? ' %' : ` ${esc(x.unidad || '')}`}</b>`;
    return `<b>${esc(x.texto_corto || '')}</b>`;
  };
  const baseCifra = (b) => (Array.isArray(b)
    ? `Base de área: ${b.map((k) => (bases[k] ? `<span title="${escH(T.limpio(bases[k].que))}">${fmt(bases[k].m2)} m² (${esc(BASE_CORTA[k] || k)})</span>` : '')).filter(Boolean).join(' · ')}`
    : esc(b || ''));
  const hCifras = `<div class="tc-cifras">${(c.resumen_para_la_web?.cifras || []).map((x) => `<div class="tc-cifra">
      <span class="tc-tit">${esc(x.titulo)}</span>${valorCifra(x)}
      <p class="tc-txt">${esc(x.texto)}</p>
      <p class="tc-base">${baseCifra(x.base_area)} · <span class="tag">${esc(x.tipo_dato)}</span></p>
      <details class="fold tc-metodo"><summary class="note">Método</summary><p class="note">${esc(x.metodo)}</p></details></div>`).join('')}</div>
    ${c.resumen_para_la_web?.nota ? `<p class="note">${esc(c.resumen_para_la_web.nota)}</p>` : ''}`;

  // 3. ambiente por ambiente: dos veredictos («frente al tipo» y «frente a la Res. 1633»)
  const filas = c.contraste_ambientes || [];
  const conTipo = filas.filter((f) => f.veredicto_tipo), sinTipo = filas.filter((f) => !f.veredicto_tipo);
  const ley = (titulo, pl) => `<p class="tc-ley"><span>${esc(titulo)}:</span> ${VEREDICTOS.map((k) => pill(k, pl ? pl[k] : k)).join(' ')}</p>`;
  const minimo = (f) => `${m2(f.m2_min_1633)}${f.m2_min_comparado != null && !num(f.m2_min_1633) ? ` <small class="note">(se compara con ${fmt(f.m2_min_comparado)} m²)</small>` : ''}<br><small class="note">${esc(f.cita_1633)}</small>`;
  const norma = (f) => (f.veredicto_norma ? `${pill(f.veredicto_norma)}${f.norma_por_confirmar || f.por_confirmar ? ' <small class="note">por confirmar</small>' : ''}` : `<small class="note">${esc(f.sin_veredicto_norma || 'sin mínimo de área')}</small>`);
  const lectura = (f) => `<details class="fold tc-mas"><summary class="note">Por qué</summary><p class="note">${esc(f.lectura)}${f.metodo_norma ? ` <b>Frente a la Res. 1633:</b> ${esc(f.metodo_norma)}` : ''}${f.nota_norma ? ` ${esc(f.nota_norma)}` : ''}${f.nota_recinto ? ` ${esc(f.nota_recinto)}` : ''}</p></details>`;
  const filaTipo = (f) => `<tr><td><b>${esc(f.ambiente_torre)}</b><br><small class="note">${esc(f.servicio)}</small>${lectura(f)}</td>
      <td data-th="Proyecto tipo" class="ancho">${esc(f.ambiente_tipo)}<br><small class="note">${esc(f.fuente_tipo)}</small></td>
      <td class="n" data-th="m² tipo">${m2(f.m2_tipo)}</td><td class="n" data-th="m² torre">${m2(f.m2_torre)}</td>
      <td data-th="Mínimo Res. 1633" class="ancho">${minimo(f)}</td>
      <td data-th="Frente al tipo">${pill(f.veredicto_tipo)}</td><td data-th="Frente a la Res. 1633">${norma(f)}</td>
      <td data-th="Recorrido" class="${f.ver_en_3d && verEn3D ? '' : 'sin-ficha'}">${boton(f.ver_en_3d, f.ambiente_torre)}</td></tr>`;
  const filaSin = (f) => `<tr><td><b>${esc(f.ambiente_torre)}</b><br><small class="note">${esc(f.servicio)}</small>${lectura(f)}</td>
      <td class="n" data-th="m² torre">${m2(f.m2_torre)}</td><td data-th="Mínimo Res. 1633" class="ancho">${minimo(f)}</td>
      <td data-th="Frente a la Res. 1633">${norma(f)}</td>
      <td data-th="Recorrido" class="${f.ver_en_3d && verEn3D ? '' : 'sin-ficha'}">${boton(f.ver_en_3d, f.ambiente_torre)}</td></tr>`;
  const cv = c.conteos_veredictos || {};
  const hAmb = `${ley('Frente al proyecto tipo', PLURAL)}${ley('Frente a la Res. 1633', PLURAL_NORMA)}
    <p class="note">Solo ${cv.con_ambiente_tipo ?? conTipo.length} de los ${cv.filas ?? filas.length} ambientes comparados tienen un equivalente en el proyecto tipo; los demás se comparan solo con el mínimo de área de la Res. 1633 de 2025. En el recorrido 3D, la capa «Comparar con el proyecto tipo» tiñe los primeros y deja en gris los que no tienen equivalente.</p>
    <div class="tbl-wrap"><table class="fichas tc-tabla"><thead><tr><th>Ambiente de la torre</th><th>Proyecto tipo</th><th class="n">m² tipo</th><th class="n">m² torre</th><th>Mínimo Res. 1633</th><th>Frente al tipo</th><th>Frente a la Res. 1633</th><th><span class="tc-oculto">Recorrido</span></th></tr></thead>
    <tbody>${conTipo.map(filaTipo).join('')}</tbody></table></div>
    <details class="fold"><summary>Ambientes sin equivalente en los proyectos tipo (${sinTipo.length}): solo frente a la Res. 1633</summary>
    <div class="tbl-wrap"><table class="fichas tc-tabla"><thead><tr><th>Ambiente de la torre</th><th class="n">m² torre</th><th>Mínimo Res. 1633</th><th>Frente a la Res. 1633</th><th><span class="tc-oculto">Recorrido</span></th></tr></thead>
    <tbody>${sinTipo.map(filaSin).join('')}</tbody></table></div>
    <p class="note">${esc(c.convenciones?.sin_ambiente_equivalente || '')}</p></details>`;

  // 4. costo por m²: barras con el método y las dos bases del tipo a la vista
  const cm = c.costo_m2 || {}, barras = cm.barras || [], max = Math.max(1, ...barras.map((b) => b.cop_m2 || 0));
  const hCosto = `<div class="tc-barras" role="list">${barras.map((b) => `<div class="tc-barra" role="listitem" data-quien="${escH(b.quien)}">
      <span class="tc-bl">${esc(b.que)}${b.base && bases[b.base] && !String(b.que).includes(fmt(bases[b.base].m2)) ? ` <small class="note">sobre ${fmt(bases[b.base].m2)} m²</small>` : ''}${b.nota ? ` <small class="note">${esc(b.nota)}</small>` : ''}</span>
      <span class="bar" aria-hidden="true"><i style="width:${((100 * (b.cop_m2 || 0)) / max).toFixed(1)}%"></i></span><span class="v">${pesos(b.cop_m2)}</span></div>`).join('')}</div><p class="note">Pesos de 2026 por m², cada uno sobre el área que se indica.</p>
    ${cm.rango_obra_civil ? `<p>La obra civil de la torre cuesta <b>entre ${fmtF(cm.rango_obra_civil.pct_mas?.[0])} % y ${fmtF(cm.rango_obra_civil.pct_mas?.[1])} % más por m²</b> que el proyecto tipo: depende de si el tipo se divide por los ${fmt(bases.tipo_presupuesto?.m2)} m² de su presupuesto (${pesos(cm.rango_obra_civil.tipo_cop_m2?.[0])}, la cifra de ${esc('$5,42 M')} que usa el estudio de la torre) o por sus ${fmt(bases.tipo_texto?.m2)} m² construidos (${pesos(cm.rango_obra_civil.tipo_cop_m2?.[1])}). Las dos son la misma obra del tipo con dos áreas distintas. <span class="tag">${esc(cm.rango_obra_civil.tipo_dato)}</span></p>` : ''}
    <details class="fold"><summary>Método, advertencias y comparación por capítulo</summary>
      <ol class="tc-lista">${(cm.metodo || []).map((x) => `<li>${esc(String(x).replace(/^\d+\.\s*/, ''))}</li>`).join('')}</ol>
      ${(cm.advertencias || []).length ? `<ul class="tc-lista">${cm.advertencias.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      <div class="tbl-wrap"><table class="fichas"><thead><tr><th>Grupo de capítulos</th><th class="n">Tipo, por m² (sobre ${fmt(bases.tipo_presupuesto?.m2)} m²)</th><th class="n">Torre, por m² con AIU (sobre ${fmt(bases.proyecto_construido?.m2)} m²)</th><th class="n">Torre / tipo</th></tr></thead><tbody>
      ${(cm.por_capitulo || []).map((x) => `<tr><td>${esc(x.grupo)}</td><td class="n" data-th="Tipo por m²">${pesos(x.tipo_dnp_por_m2_2026_sobre_269_6)}</td><td class="n" data-th="Torre por m²">${pesos(x.torre_por_m2_con_aiu_sobre_3620_6)}</td><td class="n" data-th="Torre / tipo">${num(x.razon_torre_sobre_tipo) ? `${fmt(x.razon_torre_sobre_tipo)} veces` : '—'}</td></tr>`).join('')}
      </tbody></table></div>${cm.lectura ? `<p class="note">${esc(cm.lectura)}</p>` : ''}</details>`;

  // 5. dotación por ambiente: lo que trae el tipo, lo que trae la torre, faltantes y sobrantes
  const fit = c.fuentes_items_tipo || {};
  const parFila = (p) => `<tr><td>${p.item_tipo ? esc(p.item_tipo) : '<span class="note">—</span>'}</td>
      <td data-th="En la torre" class="ancho">${(p.items_torre || []).length ? p.items_torre.map(nombreLinea).join('; ') : '<span class="note">—</span>'}${p.cierre_brechas ? `<br><small class="note">En el cierre de brechas: ${nombreLinea(p.cierre_brechas)}</small>` : ''}</td>
      <td data-th="Estado">${pill(p.estado === 'sobra' ? 'sobra' : p.estado, ESTADO_PAR[p.estado] || p.estado)}</td>
      <td data-th="Nota" class="${p.nota ? 'ancho' : 'sin-ficha'}">${p.nota ? `<small class="note">${esc(p.nota)}</small>` : ''}</td></tr>`;
  const costoFila = (f) => {
    const u = f.unidades_comparables || {}, ct = f.costo_tipo_dnp_cop_2026, tt = f.costo_torre_cop_2026;
    const tipoTxt = num(ct) ? `${pesosM(ct)}${u.tipo ? ` (${u.tipo === 1 ? `un ${esc(u.que || 'ambiente')}` : `${u.tipo} ${esc(u.que || '')}`})` : ''}` : 'sin costo propio en el tipo';
    const torreTxt = num(tt) ? `${pesosM(tt)}${num(u.torre) && u.torre > 1 ? `: ${pesosM(tt / u.torre)} por ${esc(u.que || 'unidad')} (${u.torre} en la torre)` : ''}` : 'se calcula al publicar con los precios de la dotación';
    const razon = num(tt) && num(ct) && num(u.torre) && num(u.tipo) && ct > 0 ? ` · razón por ${esc(u.que || 'unidad')}: ${fmt((tt / u.torre) / (ct / u.tipo))} veces` : '';
    return `<p class="tc-sub"><b>Tipo DNP:</b> ${tipoTxt} · <b>Torre:</b> ${torreTxt}${razon}</p>
      <p class="note">${esc(f.alcance_torre)} ${esc(c.tipo_dato_dotacion_por_ambiente?.torre || '')}</p>`;
  };
  const hDot = (c.dotacion_por_ambiente || []).map((f) => `<details class="fold tc-dot"><summary>${esc(f.ambiente)} ${f.veredicto_tipo ? pill(f.veredicto_tipo) : '<span class="tc-v" data-v="sin">sin equivalente en el tipo</span>'}</summary>
      ${costoFila(f)}
      ${(f.items_tipo || []).length ? `<p class="tc-sub"><b>Lo que trae el tipo</b> <small class="note">(${esc(fit[f.fuente_items_tipo] || f.fuente_items_tipo)})</small></p><p class="note">${f.items_tipo.map(esc).join(' · ')}</p>` : `<p class="note">${esc(fit[f.fuente_items_tipo] || f.fuente_items_tipo)}</p>`}
      ${(f.pares || []).length ? `<div class="tbl-wrap"><table class="fichas tc-pares"><thead><tr><th>Ítem del tipo</th><th>En la torre</th><th>Estado</th><th>Nota</th></tr></thead><tbody>${f.pares.map(parFila).join('')}</tbody></table></div>` : ''}
      <p class="note">${esc(f.lectura)}${f.nota_veredicto ? ` ${esc(f.nota_veredicto)}` : ''}</p>
      ${boton(f.ver_en_3d, f.ambiente)}</details>`).join('');

  // 6. escalamiento por servicio
  const es = c.escalamiento || {};
  const hEsc = `<details class="fold"><summary>Escalamiento: cuántos módulos del tipo caben en cada servicio de la torre</summary>
    <p class="note">${esc(es.metodo)}</p>
    <div class="tbl-wrap"><table class="fichas"><thead><tr><th>Servicio (piso)</th><th class="n">m² útiles</th><th>Módulo del tipo equivalente</th><th class="n">Módulos DNP por área útil</th><th class="n">Por área construida</th></tr></thead><tbody>
    ${(es.por_servicio || []).map((x) => `<tr><td>${esc(x.servicio_torre)} <small class="note">(piso ${esc(x.piso)})</small>${x.equivalencia_funcional ? `<br><small class="note">${esc(x.equivalencia_funcional)}</small>` : ''}</td><td class="n" data-th="m² útiles">${fmt(x.m2_util_torre, 1)}</td><td data-th="Módulo tipo" class="ancho">${esc(x.modulo_tipo_equivalente)}</td><td class="n" data-th="Por área útil">${fmt(x.modulos_dnp_por_area_util)}</td><td class="n" data-th="Por área construida">${fmt(x.modulos_dnp_por_area_construida)}</td></tr>`).join('')}
    </tbody></table></div>
    <ul class="tc-lista">${(es.totales || []).map((x) => `<li>${esc(x.medida)}: <b>${fmt(x.veces)} veces</b></li>`).join('')}</ul>
    <p class="note">${esc(es.lectura)} ${esc(es.relacion_con_proyecto_tipo_json || '')}</p></details>`;

  // 7. temas por capítulo (plegados)
  const hCap = `<details class="fold"><summary>Tema por tema (${(c.contraste_capitulos || []).length})</summary>
    ${(c.contraste_capitulos || []).map((x) => `<details class="fold tc-tema"><summary>${esc(x.tema)} ${pill(x.veredicto)}${x.por_confirmar ? ' <small class="note">por confirmar</small>' : ''}</summary>
      <p class="tc-sub"><b>Proyecto tipo:</b> ${esc(x.tipo)}</p><p class="tc-sub"><b>Torre:</b> ${esc(x.torre)}</p>
      <p class="note">${esc(x.explicacion)} <span class="tag">${esc(x.tipo_dato)}</span></p></details>`).join('')}</details>`;

  // 8. inconsistencias, conclusiones y fuentes
  const hInc = `<ul class="tc-lista">${(c.inconsistencias_detectadas || []).map((x) => `<li><b>${esc(x.que)}</b>${x.propuesta ? ` ${esc(x.propuesta)}` : ''}<br><small class="note">${esc(x.estado)}${x.nota_revision ? ` · ${esc(x.nota_revision)}` : ''}</small></li>`).join('')}</ul>`;
  const hFin = `<details class="fold"><summary>Conclusiones, incertidumbres y fuentes</summary>
    <ul class="tc-lista">${(c.conclusiones || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    <p class="tc-sub"><b>Lo que falta confirmar</b></p><ul class="tc-lista">${(c.incertidumbres || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
    <p class="tc-sub"><b>Fuentes</b></p><ul class="tc-lista">${(c.fuentes || []).map((x) => `<li>${x.url ? `<a href="${escH(x.url)}" target="_blank" rel="noopener">${esc(x.titulo)}</a>` : esc(x.titulo)}${x.uso ? ` <small class="note">${esc(x.uso)}</small>` : ''}</li>`).join('')}</ul></details>`;

  el.innerHTML = `<div class="tc">
    <section>${hRef}</section>
    <section><h4>Las cifras del contraste</h4>${hCifras}</section>
    <section><h4>Ambiente por ambiente</h4>${hAmb}</section>
    <section><h4>Costo por m²</h4>${hCosto}</section>
    <section><h4>Dotación por ambiente</h4><p class="note">Lo que trae el proyecto tipo en cada ambiente frente a lo que trae la torre, con los faltantes y lo que la torre agrega. El valor de la torre se calcula con los precios de su dotación; el del tipo es el del DNP llevado a pesos de 2026.</p>${hDot}</section>
    <section><h4>Escala y temas</h4>${hEsc}${hCap}</section>
    <section><h4>Inconsistencias detectadas</h4>${hInc}</section>
    <section>${hFin}<p class="note">Pesos constantes de 2026 (IPC del DANE). Las cifras de la investigación son del 23-oct-2026; los conteos de ambientes se rehicieron el 24-oct-2026 con los dos veredictos. Las fuentes oficiales del proyecto tipo no se pudieron abrir de nuevo: cotejar con el PDF del DNP.</p></section>
  </div>`;

  if (el._tcClick) el.removeEventListener('click', el._tcClick);
  el._tcClick = (ev) => {
    const b = ev.target.closest?.('[data-ver3d]');
    if (!b || !el.contains(b) || !verEn3D) return;
    const recinto = b.getAttribute('data-ver3d');
    verEn3D({ piso: pisoDe(recinto), recinto });
  };
  el.addEventListener('click', el._tcClick);
}

// ---------------------------------------------------------------------------------------------------------------------
// Capa del recorrido: color de cada recinto con veredicto frente al tipo (D la pasa a C como Map<string, THREE.Color>)
// ---------------------------------------------------------------------------------------------------------------------
export function coloresRecintos(c, plantas) {
  const out = new Map();
  if (!c || !plantas) return out;
  const col = { ...COLORES_3D, ...(c.capa_contraste_3d?.colores_3d || {}) };
  const porFila = new Map();
  for (const f of c.contraste_ambientes || []) {
    if (!f.veredicto_tipo || !VEREDICTOS.includes(f.veredicto_tipo)) continue;
    const texto = `${f.veredicto_tipo === 'cumple igual' ? 'Igual' : f.veredicto_tipo[0].toUpperCase() + f.veredicto_tipo.slice(1)} frente al proyecto tipo: `
      + `${TEXTOS.limpio(f.ambiente_tipo)}${num(f.m2_tipo) ? ` (${fmt(f.m2_tipo)} m²)` : ''}; en la torre, ${num(f.m2_torre) ? `${fmt(f.m2_torre)} m²` : TEXTOS.limpio(String(f.m2_torre ?? '—'))}`;
    for (const a of f.ambientes_programa || []) if (a && num(a.fila) && !porFila.has(a.fila)) porFila.set(a.fila, { veredicto_tipo: f.veredicto_tipo, color_hex: col[f.veredicto_tipo], texto });
  }
  for (const nv of plantas.niveles || []) {
    for (const r of nv.recintos || []) {
      const v = num(r.fila) ? porFila.get(r.fila) : null;
      if (v) out.set(r.id, { ...v });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------------
// Área equivalente del puesto tipo en 3D: placa de un piso de 320,6 m² (cuadrada, 17,9 m de lado), centrada en el origen.
// La planta real del tipo está en el PDF del DNP, que no se pudo abrir: la forma queda por confirmar (9.2).
// ---------------------------------------------------------------------------------------------------------------------
export function modeloTipo3D(THREE, c) {
  const bases = c?.resumen_para_la_web?.bases_de_area || {};
  const area = num(bases.tipo_texto?.m2) ? bases.tipo_texto.m2 : 320.6;
  const veces = (c?.resumen_para_la_web?.cifras || []).find((x) => x.id === 'tamano')?.valor;
  const lado = Math.sqrt(area), alto = 4.36, losa = 0.3;
  const color = c?.capa_contraste_3d?.colores_3d?.['cumple igual'] || COLORES_3D['cumple igual'];
  const g = new THREE.Group();
  g.name = 'proyecto_tipo_dnp';
  const placa = new THREE.Mesh(new THREE.BoxGeometry(lado, losa, lado), new THREE.MeshStandardMaterial({ color, roughness: 0.85 }));
  placa.position.y = losa / 2;
  placa.castShadow = placa.receiveShadow = true;
  const cajaG = new THREE.BoxGeometry(lado, alto - losa, lado);
  const vol = new THREE.Mesh(cajaG, new THREE.MeshStandardMaterial({ color, roughness: 0.8, transparent: true, opacity: 0.28, depthWrite: false }));
  vol.position.y = losa + (alto - losa) / 2;
  const borde = new THREE.LineSegments(new THREE.EdgesGeometry(cajaG), new THREE.LineBasicMaterial({ color: '#2f4f6f' }));
  borde.position.copy(vol.position);
  g.add(placa, vol, borde);
  g.userData.alto = alto;
  g.userData.area_m2 = area;
  g.userData.etiqueta = `<b>Área equivalente del puesto tipo DNP 2018</b><br><small>${fmt(area, 1)} m², 1 piso${num(veces) ? ` · la torre es ${fmtF(veces)} veces` : ''}</small>`;
  return g;
}
