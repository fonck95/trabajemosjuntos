// Tarjeta «Dotación para la habilitación, servicio por servicio» (equipo C; especificación de integración, 4.8, 6.1, 6.2 y
// 16.4): la matriz de cumplimiento en dotación e infraestructura de la Res. 3100 por servicio, con su alcance siempre a la
// vista (no evalúa talento humano, historia clínica ni interdependencia: no dice si un servicio se puede habilitar), cada
// exigencia con las unidades que la cubren («Ir a» en el recorrido 3D) y las faltantes, que el recorrido resalta en 3D
// con la malla del cierre de brechas. Los textos de los datos pasan por textos.esc (13.6).
import { fmtCOP, fmtN } from '../../core.js';
import { verificacion as nivelVerificacion } from './textos.js';

const ESTADOS = { cumple: 'cumple', parcial: 'parcial', falta: 'falta', documento_pendiente: 'documento pendiente', no_aplica: 'no aplica' };
const CLASE_ESTADO = { cumple: 'hab-ok', parcial: 'hab-parcial', falta: 'hab-falta', documento_pendiente: 'hab-doc', no_aplica: 'hab-na' };
const ESTANDAR = { dotacion: 'Dotación', infraestructura: 'Infraestructura', medicamentos_dispositivos: 'Medicamentos, dispositivos e insumos', procesos_prioritarios: 'Procesos prioritarios', todos_los_servicios: 'Todos los servicios' };
const palabras = (s) => String(s ?? '').replace(/_/g, ' ');

export function pintarHabilitacion(el, habilitacion, inventario, { verEn3D, textos } = {}) {
  if (!el) return;
  const { esc, escH } = textos || { esc: (s) => String(s ?? ''), escH: (s) => String(s ?? '') };
  if (!habilitacion) {
    el.innerHTML = '<p class="note">La matriz de cumplimiento en dotación e infraestructura todavía no se publicó. Esta revisión no incluye talento humano, historia clínica ni interdependencia: no dice si un servicio se puede habilitar.</p>';
    return;
  }
  const H = habilitacion, servicios = H.servicios || [];
  // unidades del inventario: nombre y recinto (para las listas «Ir a»)
  const U = new Map(), porLinea = new Map(), nombreRecinto = new Map();
  if (inventario) {
    const cols = inventario.columnas_unidades || [], c = Object.fromEntries(cols.map((k, i) => [k, i])), x = inventario.unidades_extra || {};
    (inventario.unidades || []).forEach((f, i) => {
      const l = inventario.lineas?.[f[c.linea_idx]] || {};
      const u = { id: f[c.id], nombre: x[String(i)]?.n || l.nombre || f[c.id], recinto: f[c.recinto], linea: l.id, estado: f[c.estado] };
      U.set(String(u.id), u);
      if (!porLinea.has(l.id)) porLinea.set(l.id, []);
      porLinea.get(l.id).push(u);
    });
  }
  const corte = { valor: 'corte_2026' }, escenario = { valor: 'dotacion_actual' };
  const fechas = Object.fromEntries((H.fecha_referencia || []).map((f) => [f.id, f]));
  const fechaTxt = (id) => { const f = fechas[id]; if (!f) return ''; const [a, m, d] = String(f.fecha).split('-'); return `${+d} de ${['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][+m - 1]} de ${a}`; };
  const estadoDe = (e) => e.estado?.[corte.valor]?.[escenario.valor] || 'no_aplica';
  const pill = (est) => `<span class="pill ${CLASE_ESTADO[est] || ''}">${esc(ESTADOS[est] || palabras(est))}</span>`;
  const ir = (destino, txt, etiqueta) => (verEn3D ? `<button type="button" class="reco-ir" data-ver="${escH(JSON.stringify(destino))}" aria-label="${escH(etiqueta || txt)}">${esc(txt)}</button>` : '');
  const enlace = (url) => (/^https?:\/\//.test(String(url || '')) ? ` <a href="${escH(url)}" target="_blank" rel="noopener">fuente</a>` : '');

  function filaExigencia(e) {
    const est = estadoDe(e), uu = (e.unidades || []).map((id) => U.get(String(id)) || { id, nombre: id });
    const fantasmas = (e.cierre_de_brechas || []).flatMap((l) => porLinea.get(l) || []).filter((u) => u.estado === 'cierre_brechas_propuesto');
    const texto = e.texto_disponible ? `«${esc(e.texto_corto || e.que_exige || '')}»` : `${esc(e.que_exige || e.texto_corto || '')} <small class="note">(resumen; texto oficial no obtenido)</small>`;
    const unidadesHTML = uu.length ? `<details class="fold"><summary>Unidades que la cubren (${fmtN(uu.length)})</summary><ul class="tight hab-unidades">${uu.map((u) => `<li>${esc(u.nombre)}${u.recinto && nombreRecinto.get(u.recinto) ? ` <small class="note">${esc(nombreRecinto.get(u.recinto))}</small>` : ''} ${ir({ unidad: u.id }, 'Ir a', `Ir a ${u.nombre} en el recorrido 3D`)}</li>`).join('')}</ul></details>` : '';
    const cierre = (e.cierre_de_brechas || []).length ? `<p class="hab-cierre"><small>Cierre de brechas propuesto: ${esc((e.cierre_de_brechas || []).map((l) => porLinea.get(l)?.[0]?.nombre || l).join('; '))}</small> ${fantasmas.length ? ir({ unidad: fantasmas[0].id, faltantes: true, resaltar: fantasmas.map((u) => u.id) }, 'Ver faltantes en 3D', 'Ver en el recorrido 3D lo que falta para esta exigencia') : ''}</p>` : '';
    return `<li class="hab-ex">
      <div class="hab-ex-c">${pill(est)} <b>${esc(String(e.numeral || e.id))}</b> <small class="note">· ${esc(ESTANDAR[e.estandar] || palabras(e.estandar))} · ${esc(e.exigible === 'si' ? 'exigible' : e.exigible === 'por_confirmar' ? 'por confirmar' : palabras(e.exigible))}</small></div>
      <p>${texto}</p>
      <p class="note"><small>${esc(nivelVerificacion(e.verificacion_texto || 'por_confirmar'))}${enlace(e.fuente_url)}${e.requerido != null ? ` · se requieren ${fmtN(e.requerido)}; hay ${fmtN(e.encontrado?.dotacion_actual ?? 0)}${e.encontrado?.con_cierre_de_brechas != null && e.encontrado.con_cierre_de_brechas !== e.encontrado.dotacion_actual ? ` (${fmtN(e.encontrado.con_cierre_de_brechas)} con el cierre)` : ''}` : ''}${e.nota_estado ? ` · ${esc(e.nota_estado)}` : ''}</small></p>
      ${cierre}${unidadesHTML}
    </li>`;
  }
  const resumenServicio = (s) => {
    const r = s.resumen?.[corte.valor]?.[escenario.valor] || {}, ex = r.exigibles || {}, pc = r.por_confirmar || {};
    const sum = (o) => Object.values(o).reduce((a, b) => a + (+b || 0), 0);
    return { ex, pc, nEx: sum(ex), nPc: sum(pc) };
  };
  function pintar() {
    const falt = Object.fromEntries((H.faltantes_por_servicio?.tabla || []).map((f) => [f.servicio, f]));
    el.querySelector('.hab-tabla tbody').innerHTML = servicios.map((s) => {
      const { ex, nEx, nPc } = resumenServicio(s), f = falt[s.id];
      return `<tr><td><a href="#hab-${escH(s.id)}" data-abrir="${escH(s.id)}">${esc(s.nombre)}</a></td>
        <td class="n" data-th="Cumplen">${fmtN(ex.cumple || 0)}</td><td class="n" data-th="Parciales">${fmtN(ex.parcial || 0)}</td>
        <td class="n${ex.falta ? ' hab-falta-n' : ''}" data-th="Faltan">${fmtN(ex.falta || 0)}</td><td class="n" data-th="Documento pendiente">${fmtN(ex.documento_pendiente || 0)}</td>
        <td class="n" data-th="Exigibles">${fmtN(nEx)}</td><td class="n" data-th="Por confirmar">${fmtN(nPc)}</td>
        <td class="n" data-th="Cierre propuesto">${f && f.items_cierre ? `${fmtN(f.items_cierre)} ítems · ${fmtCOP(f.inversion_con_precio_cop_2026 || 0)}` : '—'}</td></tr>`;
    }).join('');
    // los servicios ya abiertos se vuelven a pintar con el corte y el escenario elegidos
    el.querySelectorAll('details.hab-srv[open]').forEach((d) => llenar(d));
  }
  function llenar(d) {
    const s = d.dataset.srv === '__todos' ? { exigencias: H.todos_los_servicios?.detalle || [] } : servicios.find((x) => x.id === d.dataset.srv);
    const cuerpo = d.querySelector('.hab-cuerpo');
    const L = s?.exigencias || [];
    const orden = { falta: 0, parcial: 1, documento_pendiente: 2, cumple: 3, no_aplica: 4 };
    cuerpo.innerHTML = `<ul class="hab-lista">${[...L].sort((a, b) => (orden[estadoDe(a)] ?? 5) - (orden[estadoDe(b)] ?? 5)).map(filaExigencia).join('')}</ul>`;
  }
  el.innerHTML = `<div class="hab">
      <p class="hab-alcance"><b>Alcance.</b> ${esc(H.texto_alcance || '')}</p>
      <p class="note">${esc(H.aviso_vigencia || '')} ${esc(H.aviso_textos || '')}</p>
      <div class="hab-ctl">
        <div class="seg wrap-seg" role="group" aria-label="Fecha de corte" data-g="corte">
          <button type="button" data-v="corte_2026" aria-pressed="true">Hoy (${esc(fechaTxt('corte_2026'))})</button>
          <button type="button" data-v="apertura" aria-pressed="false">A la apertura (${esc(fechaTxt('apertura'))}, estimación)</button>
        </div>
        <div class="seg wrap-seg" role="group" aria-label="Escenario" data-g="escenario">
          <button type="button" data-v="dotacion_actual" aria-pressed="true">Con la dotación actual</button>
          <button type="button" data-v="con_cierre_de_brechas" aria-pressed="false">Con el cierre de brechas propuesto</button>
        </div>
      </div>
      <p class="note">El estado es el <b>cumplimiento en dotación e infraestructura</b> de cada exigencia: cumple, parcial, falta o documento pendiente (lo elabora la E.S.E.). Las exigencias «por confirmar» se cuentan aparte.</p>
      <div class="tbl-wrap"><table class="fichas hab-tabla"><thead><tr><th>Servicio</th><th class="n">Cumplen</th><th class="n">Parciales</th><th class="n">Faltan</th><th class="n">Documento pendiente</th><th class="n">Exigibles</th><th class="n">Por confirmar</th><th class="n">Cierre propuesto</th></tr></thead><tbody></tbody></table></div>
      <div class="hab-servicios">
        ${servicios.map((s) => `<details class="fold hab-srv" id="hab-${escH(s.id)}" data-srv="${escH(s.id)}"><summary>${esc(s.nombre)} <small class="note">${esc(s.marco || '')}</small></summary><div class="hab-cuerpo"></div></details>`).join('')}
        ${(H.todos_los_servicios?.detalle || []).length ? `<details class="fold hab-srv" data-srv="__todos"><summary>Exigencias de todos los servicios <small class="note">(${fmtN(H.todos_los_servicios.detalle.length)})</small></summary><div class="hab-cuerpo"></div></details>` : ''}
      </div>
    </div>`;
  el.querySelectorAll('[data-g]').forEach((g) => g.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-v]');
    if (!b) return;
    g.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    (g.dataset.g === 'corte' ? corte : escenario).valor = b.dataset.v;
    pintar();
  }));
  el.addEventListener('toggle', (ev) => { const d = ev.target; if (d.matches?.('details.hab-srv') && d.open) llenar(d); }, true);
  el.addEventListener('click', (ev) => {
    const a = ev.target.closest('[data-abrir]');
    if (a) { ev.preventDefault(); const d = el.querySelector(`details[data-srv="${CSS.escape(a.dataset.abrir)}"]`); if (d) { d.open = true; d.scrollIntoView({ block: 'nearest' }); d.querySelector('summary')?.focus(); } return; }
    const b = ev.target.closest('[data-ver]');
    if (b && verEn3D) { try { verEn3D(JSON.parse(b.dataset.ver)); } catch { /* destino mal formado */ } }
  });
  // nombres de recintos (para las listas de unidades); si la planta no está, se omiten
  pintar();
  return { refrescar: pintar, nombresRecintos(m) { for (const [k, v] of m) nombreRecinto.set(k, v); } };
}
