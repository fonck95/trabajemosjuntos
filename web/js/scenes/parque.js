// Escena 3D y fichas del parque ecológico y tecnológico sobre el relleno sanitario Las Américas: "Hoy" (el relleno) y
// "Con el parque" (granja solar sobre las celdas clausuradas, coworking rural, granja, circuito y humedal), modelo generado
// desde data/edificios/relleno_parque.json. Los datos (diagnóstico, energía y hogares de estratos 1 y 2, programa,
// presupuesto y financiación) vienen de data/proyectos/parque_relleno/ y se cargan aparte (data/parque.json).
import { THREE, Stage, tokens, onTheme, mat, fmtN, fmtCOP, gsap, solidBox } from '../core.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS } from '../data.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mill = (v) => (v == null ? '—' : fmtCOP(+v * 1e6));
// rango de plata: si se parte, la «a» baja pegada a la segunda cifra (no queda sola en un renglón)
const rangoM = (r) => (Array.isArray(r) ? `${mill(r[0])} a\u00a0${mill(r[1])}` : mill(r));
// corta en el último espacio antes de n caracteres (no a mitad de palabra)
const corto = (t, n) => { t = String(t ?? '').trim(); if (t.length <= n) return t; const i = t.lastIndexOf(' ', n - 1); return `${t.slice(0, i > 0 ? i : n - 1).replace(/[,;:]$/, '')}…`; };
const CERTEZA = { calculo_propio: 'cálculo propio', estimacion: 'estimación', dato_oficial: 'dato oficial', cotizacion: 'cotización' };
const certeza = (k) => CERTEZA[k] || String(k).replace(/_/g, ' ');
const web = (u) => /^https?:\/\//.test(String(u || ''));   // solo se enlazan páginas públicas, no archivos del proyecto
// «Hoy»: lo que hay en el relleno, con su centro en el marco local del modelo (metros; x al oriente, y al norte)
const HOY = [
  ['Celda occidental', 'disposición reciente, con material de cobertura', [-54, 30]],
  ['Celda oriental', 'frente de disposición activo', [66, 19]],
  ['Celda norte', 'probablemente clausurada, con pasto', [23, 48]],
  ['Lagunas de lixiviados', 'cuatro piscinas', [-8, -3]],
  ['Vía de acceso en afirmado', '', [-80, 65]],
  ['Portería de la entrada norte', '', [-27, 143]],
];
// "x −81 a 138, y −8 a 118" → centro [x, y] en el marco de la especificación
const centroDe = (s) => {
  if (Array.isArray(s) && s.length === 2) return s.map(Number);
  const pt = String(s || '').match(/^\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]\s*$/);
  if (pt) return [+pt[1], +pt[2]];
  const n = String(s || '').replace(/−/g, '-').match(/x\s*(-?[\d.,]+)\s*a\s*(-?[\d.,]+).*?y\s*(-?[\d.,]+)\s*a\s*(-?[\d.,]+)/i);
  if (!n) return null;
  const v = n.slice(1).map((q) => parseFloat(q.replace(',', '.')));
  return [(v[0] + v[1]) / 2, (v[2] + v[3]) / 2];
};

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [-160, 140, 190], target: [20, 0, -40], fov: 36, minDist: 10, maxDist: 900, tone: 'aces', exposure: 1.05, fit: 0.9, declutter: ['lbl-node'] });
  const T = tokens(), S = st.scene;
  const sc = st.sunLight.shadow.camera; Object.assign(sc, { left: -220, right: 220, top: 220, bottom: -220, near: 1, far: 700 });
  st.sunLight.position.set(120, 260, 90); st.sunLight.shadow.mapSize.set(2048, 2048);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(600, 64), mat(T.ground)); ground.rotation.x = -Math.PI / 2; ground.position.y = -0.06; ground.receiveShadow = true; S.add(ground); st.freeze(ground);

  const P = EDIFICIOS.find((e) => e.id === 'relleno_parque');
  let modelo = null, modo = 'parque';
  const etiquetas = [], tel = () => el.clientWidth < 560;
  const etiquetasHoy = HOY.map(([n, sub, [x, y]]) => st.label(`<b>${n}</b>${sub && !tel() ? `<br><small>${sub}</small>` : ''}`, 'lbl-node', [x, 4, -y]));
  etiquetasHoy.forEach((l) => { l.visible = false; });
  if (P?.archivo) {
    modelo = progressiveLOD([{ url: P.archivo, distance: 0 }, { url: P.archivo_lod1, distance: 700 }], () => { aplicar(); st.updateShadows(); encuadre(); });
    S.add(modelo);
  }
  // frameBox prueba distancias con una copia de la cámara: con el plano lejano de 1.200 m, en pantallas verticales ninguna
  // distancia "cabía" y la cámara se iba a 8 km (escena en blanco); se amplía antes de buscar y se ajusta a la hallada.
  // En pantallas verticales se mira desde el sur, con el lado corto del predio a lo ancho, y en «Hoy» se encuadran las celdas
  const encuadre = () => {
    if (!modelo) return;
    const box = modo === 'hoy' ? new THREE.Box3(new THREE.Vector3(-100, 0, -146), new THREE.Vector3(102, 8, 34)) : solidBox(modelo, 0.3);
    const vertical = el.clientWidth < el.clientHeight, dir = vertical ? new THREE.Vector3(-0.15, 0.8, 0.58) : new THREE.Vector3(-0.6, 0.62, 0.7);
    st.camera.far = 1e5; st.camera.updateProjectionMatrix();
    const D = st.frameBox(box, dir, { margin: vertical ? 0.96 : 0.92, duration: 1.4 });
    st.camera.far = Math.max(1200, 2 * D + box.getSize(new THREE.Vector3()).length()); st.camera.updateProjectionMatrix();
  };
  function aplicar() {
    if (modelo) modelo.traverse((o) => {
      if (o.userData.demoler) o.visible = modo === 'hoy';
      if (o.name === 'adecuaciones') o.visible = modo === 'parque';
    });
    etiquetas.forEach((l) => { l.visible = modo === 'parque'; });
    etiquetasHoy.forEach((l) => { l.visible = modo === 'hoy'; });
    st.updateShadows();
  }
  const btns = root.querySelectorAll('[data-modo-parque]');
  btns.forEach((b) => b.addEventListener('click', () => { modo = b.dataset.modoParque; btns.forEach((x) => x.setAttribute('aria-pressed', String(x === b))); aplicar(); encuadre(); }));

  const q = (s) => root.querySelector(`[data-slot="parque.${s}"]`);
  fetch(new URL('../../data/parque.json', import.meta.url)).then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (!d) return;
    // etiquetas de los componentes principales sobre el modelo
    for (const c of d.programa?.componentes || []) {
      const ce = centroDe(c.ubicacion_local_m); if (!ce || !/granja|cowork|humedal|laguna|mirador|taller|cafeter|recreo|parqueadero|plazoleta/i.test(c.componente)) continue;
      // en el teléfono solo las cinco principales: las demás están en la tabla del programa, más abajo
      if (tel() && !/granja|laguna|cowork|mirador/i.test(c.componente.replace(/control de la granja/i, ''))) continue;
      const nombre = c.componente.split(/[(:]/)[0].trim();
      etiquetas.push(st.label(`<b>${esc(nombre)}</b>${c.capacidad && !tel() ? `<br><small>${esc(corto(c.capacidad, 48))}</small>` : ''}`, `lbl-node${tel() && nombre.length > 26 ? ' wrap' : ''}`, [ce[0], 6, -ce[1]]));
    }
    aplicar();
    pintar(d);
  }).catch((e) => console.warn('parque.json', e));

  function pintar(d) {
    const en = d.energia || {}, g = en.granja || {}, cob = en.cobertura_de_hogares || {}, pr = d.presupuesto || {}, fi = d.financiacion || {};
    const c = cob.escenario_c_bloque_solar_50_kwh || {};
    q('tiles').innerHTML = `<div class="tile"><b>${fmtN(g.potencia_dc_kwp || 0, 0)} kWp</b><span>granja solar sobre las celdas (${fmtN(g.modulos || 0)} módulos)</span></div>
      <div class="tile"><b>${fmtN(c.hogares || 0)}</b><span>hogares de estratos 1 y 2 con 50 kWh/mes solares (${fmtN(c.porcentaje_de_e1_e2 || 0, 0)}&nbsp;%)</span></div>
      <div class="tile"><b>${mill(en.ahorro_anual?.si_sustituye_consumo_subsidiado?.total_al_cu_millones)}</b><span>al año entre subsidios evitados y ahorro de los hogares</span></div>
      <div class="tile"><b>${mill(pr.total_millones)}</b><span>costo total (rango ${rangoM(pr.rango_millones)})</span></div>`;
    q('energia').innerHTML = `<p>${esc(en.respuesta_corta)}</p>
      <div class="tbl-wrap"><table><thead><tr><th>Escenario</th><th class="n">Hogares</th><th class="n">kWh/mes por hogar</th></tr></thead><tbody>
      ${[['Consumo de subsistencia completo', cob.escenario_a_subsistencia_completa], ['Consumo subsidiado real', cob.escenario_b_consumo_subsidiado_real], ['Bloque solar de 50 kWh/mes (recomendado)', cob.escenario_c_bloque_solar_50_kwh]].filter(([, x]) => x).map(([n, x]) => `<tr><td>${n}</td><td class="n">${fmtN(x.hogares)}</td><td class="n">${fmtN(x.kwh_mes_por_hogar)}</td></tr>`).join('')}
      </tbody></table></div>
      ${c.ahorro_mes_estrato_1 ? `<p class="note">Con el bloque de 50 kWh/mes, un hogar de estrato 1 ahorra unos ${fmtCOP(c.ahorro_mes_estrato_1)} al mes (${fmtN((c.ahorro_relativo?.estrato_1 || 0) * 100, 0)} % de la factura) y uno de estrato 2 unos ${fmtCOP(c.ahorro_mes_estrato_2)} (${fmtN((c.ahorro_relativo?.estrato_2 || 0) * 100, 0)} %).</p>` : ''}
      ${en.figura_legal?.recomendada ? `<p class="note"><b>Figura legal:</b> ${esc(en.figura_legal.recomendada)}</p>` : ''}`;
    const dg = d.diagnostico || {};
    q('relleno').innerHTML = `<p>${esc(dg.respuesta_corta)}</p>
      ${Array.isArray(dg.clausura_requisitos) ? `<details class="fold"><summary>Lo que exige la clausura (${dg.clausura_requisitos.length})</summary><ul class="tight">${dg.clausura_requisitos.map((x) => `<li>${typeof x === 'string' ? esc(x) : `${web(x.url) ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.norma)}</a>` : esc(x.norma || '')}: ${esc(x.texto || x.requisito || '')}`}</li>`).join('')}</ul></details>` : ''}
      ${dg.alternativa_regional?.descartada ? ((a, r, rz) => `<p class="note"><b>Descartado como destino de la basura:</b> ${esc(r.sitio)}, a ${fmtN(r.distancia_via_km, 1)} km por vía (${esc(r.licencia || '')}).${a.uso_posible ? ` ${esc(a.uso_posible)}` : ''}</p>${rz.length || a.costo_de_la_decision ? `<details class="fold"><summary>Por qué se descartó${rz.length ? ` (${rz.length})` : ''}</summary>${rz.length ? `<ul class="tight">${rz.map((x) => `<li>${esc(String(x).charAt(0).toUpperCase() + String(x).slice(1))}.</li>`).join('')}</ul>` : ''}${a.costo_de_la_decision ? `<p class="note">${esc(a.costo_de_la_decision)}</p>` : ''}</details>` : ''}`)(dg.alternativa_regional, dg.alternativa_regional.descartada, dg.alternativa_regional.razones || []) : ''}`;
    const pg = d.programa || {};
    q('programa').innerHTML = `<p>${esc(pg.idea)}</p>${pg.regla_de_oro ? `<p class="note"><b>Regla:</b> ${esc(pg.regla_de_oro)}</p>` : ''}
      <table><thead><tr><th>Componente y capacidad</th><th class="n">m²</th></tr></thead><tbody>${(pg.componentes || []).map((x) => `<tr><td>${esc(x.componente)}${x.capacidad ? `<br><small class="note">${esc(x.capacidad)}</small>` : ''}</td><td class="n">${x.area_m2 ? fmtN(x.area_m2) : ''}</td></tr>`).join('')}</tbody></table>`;
    const ETQ_P = { fase_0_1_estudios_y_clausura: 'Fases 0 y 1: estudios y clausura', fase_2_granja_solar_y_conexion: 'Fase 2: granja solar y conexión', fase_3_parque: 'Fase 3: parque', fase_0_1_clausura: 'Fases 0 y 1: clausura', fase_2_granja_solar: 'Fase 2: granja solar', posclausura: 'Posclausura (monitoreo, lixiviados y gases)', operacion_parque: 'Operación del parque', om_granja_solar: 'Operación y mantenimiento de la granja solar', disposicion_regional: 'Disposición en un relleno regional', mantenimiento_ruta_ciclista_3_8_km: 'Mantenimiento de la ruta ciclista (3,8 km)', tarifa_y_provision: 'Tarifa de aseo y provisión de clausura', sgp_apsb_y_pda: 'SGP de agua y saneamiento y PDA', sgr: 'Regalías (SGR)', colombia_solar_o_fenoge: 'Colombia Solar o FENOGE', sgr_incentivo_produccion: 'SGR, incentivo a la producción', findeter_o_privado: 'Findeter o inversionista privado', deporte_tic_cultura: 'Deporte, TIC y cultura (cofinanciación nacional)', ecopetrol_y_cooperacion: 'Ecopetrol y cooperación', recursos_propios: 'Recursos propios del municipio' };
    const etq = (k) => ETQ_P[k] || k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
    const caps = pr.capitulos || [], tot = caps.map((x) => (x.items || []).reduce((a, i) => a + (+i.valor || 0), 0)), mx = Math.max(1, ...tot);
    q('presupuesto').innerHTML = `<div class="barras">${caps.map((x, i) => `<details class="fold"><summary><span class="bar-l">${esc(x.capitulo)}</span><span class="bar"><i style="width:${(100 * tot[i]) / mx}%"></i></span><span class="bar-v">${fmtCOP(tot[i])}</span></summary>
      <div class="tbl-wrap"><table class="fichas"><thead><tr><th>Ítem</th><th>Und.</th><th class="n">Cantidad</th><th class="n">Valor unitario</th><th class="n">Total</th></tr></thead><tbody>${(x.items || []).map((it) => `<tr><td>${esc(it.item)}${it.certeza ? ` <small class="note">(${esc(certeza(it.certeza))})</small>` : ''}</td><td class="sin-ficha">${esc(it.unidad)}</td><td class="n" data-th="Cantidad${it.unidad ? ` (${esc(it.unidad)})` : ''}">${fmtN(it.cantidad, 2)}</td><td class="n" data-th="Valor unitario">${fmtCOP(it.precio_unitario)}</td><td class="n" data-th="Total">${fmtCOP(it.valor)}</td></tr>`).join('')}</tbody></table></div></details>`).join('')}</div>
      <dl class="kv" style="margin-top:10px">${Object.entries(pr.por_fase_millones || {}).map(([k, v]) => `<dt>${esc(etq(k))}</dt><dd>${mill(v)}</dd>`).join('')}<dt><b>Total</b></dt><dd><b>${mill(pr.total_millones)}</b></dd></dl>
      ${pr.costos_anuales_millones ? `<details class="fold"><summary>Costos anuales de operación</summary><dl class="kv">${Object.entries(pr.costos_anuales_millones).filter(([, v]) => typeof v === 'number').map(([k, v]) => `<dt>${esc(etq(k))}</dt><dd>${mill(v)}</dd>`).join('')}</dl></details>` : ''}`;
    q('financiacion').innerHTML = `${fi.principio ? `<p class="note">${esc(fi.principio)}</p>` : ''}<table><thead><tr><th>Fuente</th><th>Monto posible</th></tr></thead><tbody>${(fi.fuentes || []).map((x) => `<tr><td><details class="fold"><summary>${esc(x.fuente)}</summary>${x.condiciones ? `<p class="note">${esc(x.condiciones)}</p>` : ''}${web(x.url) ? `<p class="note"><a href="${esc(x.url)}" target="_blank" rel="noopener">Ver la fuente</a></p>` : ''}</details>${x.para ? `<small class="note">Para: ${esc(x.para)}</small>` : ''}</td><td class="rango">${rangoM(x.monto_millones)}</td></tr>`).join('')}</tbody></table>
      ${fi.mezcla_sugerida_millones ? `<h4>Mezcla sugerida por fase</h4><dl class="kv">${Object.entries(fi.mezcla_sugerida_millones).filter(([, v]) => typeof v === 'object').map(([fase, v]) => `<dt><b>${esc(etq(fase))}</b></dt><dd>${mill(v.total)}</dd>${Object.entries(v).filter(([k]) => k !== 'total').map(([k, m]) => `<dt>&nbsp;&nbsp;${esc(etq(k))}</dt><dd>${mill(m)}</dd>`).join('')}`).join('')}</dl>` : ''}`;
  }

  onTheme((t) => { ground.material.color.copy(t.ground); });
  return st;
}
