// Importación de los Excel (se procesan y se descartan; solo quedan los datos) y exportación de la base única.
import { api, descargar } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { $, aviso, avisoError, dialogo, fecha, html, icono, montar, num } from '../ui.js';

const MAX_ARCHIVOS = 6; // el servidor procesa como máximo 6 archivos por importación
const TIPOS = { tramites: 'trámites', cedulas: 'base con cédula', planilla: 'planilla de campo' };

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
    ${r.omitidas_sin_autorizacion ? html`<p class="sec">${num(r.omitidas_sin_autorizacion)} filas de personas que no autorizaron: no se les agregó ningún dato.</p>` : ''}
    ${r.votacion_por_confirmar ? html`<p class="sec">${num(r.votacion_por_confirmar)} puestos o mesas quedaron «por confirmar» (puesto ambiguo, mesa fuera de rango o dato de otra base).</p>` : ''}
    ${r.autorizaciones_por_confirmar ? html`<div class="aviso-legal">${num(r.autorizaciones_por_confirmar)} autorizaciones «declaradas en planilla» no habilitan llamadas hasta que usted las confirme con la evidencia física (en el historial).</div>` : ''}
    ${(r.planilleros_desconocidos || []).length ? html`<div class="aviso-legal">Planilleros que no existen o no están activos: ${r.planilleros_desconocidos.join(', ')}. Sus filas quedaron con el «Capturado por» del formulario.</div>` : ''}
    ${r.no_guardadas ? html`<div class="aviso-legal">${num(r.no_guardadas)} fichas no se guardaron porque cambiaron al mismo tiempo en el panel. Vuelva a importar el archivo para completarlas.</div>` : ''}
    ${r.cedulas_en_revision || r.conflictos_cedula ? html`<p><a class="btn" href="/calidad" data-ruta>Revisar en Calidad de datos</a></p>` : ''}`;
}

export async function vistaImportar(el) {
  const [historial, catalogos] = await Promise.all([api.get('/api/importaciones'), api.get('/api/catalogos').catch(() => ({}))]);
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const planilleros = (catalogos.usuarios || []).filter((u) => u.rol === 'planillero' && u.activo !== false);
  montar(el, html`
    <div class="cabecera"><div><h1>Importar y exportar</h1><div class="sub">Suba versiones nuevas cuando quiera: nada se duplica, lo editado en el panel no se pisa y lo distinto queda como dato alterno.</div></div></div>
    <div class="rejilla r-12">
      <section class="tarjeta c-7">
        <h2>Importar archivos de Excel</h2>
        <label class="zona-subida" id="zona" style="display:block"><input type="file" id="archivos" accept=".xlsx" multiple class="sr">
          <b>Arrastre aquí los archivos .xlsx o haga clic</b>
          <span class="sec">Base de trámites por vereda, base unificada con cédula y planillas de campo. Se reconocen por sus columnas.</span></label>
        <div id="elegidos" class="chips" style="margin:12px 0"></div>
        <div class="form" style="margin-bottom:12px">
          <label class="campo"><span>Capturado por (planillas)</span><select id="capturado">
            <option value="">— Nadie / varios —</option>${planilleros.map((u) => html`<option value="${u.id}">${u.nombre || u.usuario} (${u.usuario})</option>`)}</select></label>
          <div class="campo"><span>Plantilla</span><button type="button" class="btn" id="plantilla">${icono('descargar')} Planilla de campo (.xlsx)</button></div>
        </div>
        <p class="sec" style="margin-top:0">La columna «Planillero (usuario)» de cada fila manda sobre «Capturado por».</p>
        <button class="btn primario" id="subir" disabled>Importar y cruzar</button>
        <div id="resultado" style="margin-top:16px"></div>
      </section>
      <section class="tarjeta c-5">
        <h2>Exportar</h2>
        <p class="sec">La base única completa en Excel: datos de contacto, dirección normalizada, coordenadas, precisión, necesidades, listas, reuniones y campos propios. Para exportar un grupo, aplique filtros en <a href="/personas" data-ruta>Habitantes</a> y exporte desde allí. Las exportaciones omiten a quien marcó «No autorizó» el tratamiento de sus datos.</p>
        <button class="btn oscuro" id="exportar">${icono('descargar')} Descargar base única (.xlsx)</button>
        <div class="aviso-legal" style="margin-top:16px">Cada exportación queda en la auditoría. Comparta el archivo solo por canales seguros y bórrelo cuando ya no lo necesite.</div>
      </section>
      <section class="tarjeta c-12">
        <h2>Historial de importaciones</h2>
        <div id="historial">${tablaHistorial(historial)}</div>
      </section>
    </div>`);

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
  const recargarHistorial = async () => {
    try { montar($('#historial', el), tablaHistorial(await api.get('/api/importaciones'))); } catch { /* se ve al volver a la vista */ }
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
    if (!b) return;
    const { el: d, cerrar } = dialogo({ titulo: 'Confirmar autorizaciones de esta planilla',
      cuerpo: html`<p class="sec" style="margin-top:0">${num(Number(b.dataset.n))} personas declararon en la planilla que autorizan. Al confirmarlas, se podrán contactar por los canales que eligieron. Solo se confirman las que siguen vigentes (no las revocadas después).</p>
        <label class="campo"><span>Evidencia física</span><textarea id="evidencia" maxlength="500" placeholder="Por ejemplo: planillas firmadas archivadas en la sede, carpeta 3"></textarea></label>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Confirmar</button>` });
    $('#g', d).onclick = async () => {
      const evidencia = $('#evidencia', d).value.trim();
      if (evidencia.length < 5) { aviso('Describa dónde está la evidencia', 'error'); return; }
      try {
        const r = await api.post(`/api/importaciones/${b.dataset.confirmar}/confirmar-autorizaciones`, { evidencia });
        cerrar(); aviso(`${num(r.confirmadas)} autorizaciones confirmadas`); recargarHistorial();
      } catch (err) { avisoError(err); }
    };
  });
  $('#exportar', el).addEventListener('click', async () => {
    try { await descargar('/api/exportar.xlsx'); aviso('Exportación lista'); } catch (e) { aviso(e.message, 'error'); }
  });
}
