// Importación de los Excel (se procesan y se descartan; solo quedan los datos) y exportación de la base única.
import { api, descargar } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { $, aviso, fecha, html, icono, montar, num } from '../ui.js';

const MAX_ARCHIVOS = 6; // el servidor procesa como máximo 6 archivos por importación
const TIPOS = { tramites: 'trámites', cedulas: 'base con cédula' };

const tablaHistorial = (historial) => (historial.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Fecha</th><th>Usuario</th><th>Archivos</th><th class="num">Personas nuevas</th><th class="num">Trámites nuevos</th><th class="num">Cédulas cruzadas</th><th class="num">Por revisar</th></tr></thead>
  <tbody>${historial.map((h) => html`<tr style="cursor:default"><td>${fecha(h.ts, true)}</td><td>${h.usuario}</td><td>${h.archivo}</td>
    <td class="num">${num(h.resumen.personas_nuevas)}</td><td class="num">${num(h.resumen.tramites_nuevos)}</td><td class="num">${num(h.resumen.cedulas_unidas_auto)}</td><td class="num">${num(h.resumen.cedulas_en_revision)}</td></tr>`)}</tbody></table></div>`
  : html`<p class="sec">Aún no se ha importado nada.</p>`);

export async function vistaImportar(el) {
  const historial = await api.get('/api/importaciones');
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  montar(el, html`
    <div class="cabecera"><div><h1>Importar y exportar</h1><div class="sub">Suba versiones nuevas cuando quiera: nada se duplica y lo editado en el panel no se pisa.</div></div></div>
    <div class="rejilla r-12">
      <section class="tarjeta c-7">
        <h2>Importar archivos de Excel</h2>
        <label class="zona-subida" id="zona"><input type="file" id="archivos" accept=".xlsx" multiple class="sr">
          <b>Arrastre aquí los archivos .xlsx o haga clic</b>
          <span class="sec">Base de trámites por vereda (ID, Número, Fecha, Nombre Solicitante, Dirección…) y base unificada con cédula. Se reconocen por sus columnas.</span></label>
        <div id="elegidos" class="chips" style="margin:12px 0"></div>
        <button class="btn primario" id="subir" disabled>Importar y cruzar</button>
        <div id="resultado" style="margin-top:16px"></div>
      </section>
      <section class="tarjeta c-5">
        <h2>Exportar</h2>
        <p class="sec">La base única completa en Excel: datos de contacto, dirección normalizada, coordenadas, precisión, necesidades, listas, reuniones y campos propios. Para exportar un grupo, aplique filtros en <a href="/personas" data-ruta>Habitantes</a> y exporte desde allí.</p>
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
  const zona = $('#zona', el);
  $('#archivos', el).addEventListener('change', (e) => elegir(e.target.files));
  zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('encima'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('encima'));
  zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('encima'); elegir(e.dataTransfer.files); });
  $('#subir', el).addEventListener('click', async () => {
    if (!archivos.length || archivos.length > MAX_ARCHIVOS) return;
    const fd = new FormData();
    archivos.forEach((f) => fd.append('archivos', f));
    $('#subir', el).disabled = true;
    montar($('#resultado', el), html`<div style="display:flex;gap:10px;align-items:center"><div class="giro"></div><span>Leyendo, agrupando, cruzando por nombre y georreferenciando…</span></div>`);
    try {
      const r = await api.subir('/api/importar', fd);
      const geo = r.geo.por_precision || {};
      const ubicadas = Object.entries(geo).filter(([k]) => k !== 'sin_ubicar').reduce((a, [, v]) => a + v, 0);
      montar($('#resultado', el), html`<div class="kpis" style="margin:0">
        <div class="kpi"><div class="t">Personas nuevas</div><div class="v">${num(r.personas_nuevas)}</div><div class="d">${num(r.personas_actualizadas)} actualizadas</div></div>
        <div class="kpi"><div class="t">Trámites nuevos</div><div class="v">${num(r.tramites_nuevos)}</div></div>
        <div class="kpi"><div class="t">Cédulas cruzadas</div><div class="v">${num(r.cedulas_unidas_auto)}</div><div class="d">${num(r.cedulas_en_revision)} por revisar · ${num(r.cedulas_sin_coincidencia)} sin par</div></div>
        <div class="kpi"><div class="t">Ubicadas</div><div class="v">${num(ubicadas)}</div><div class="d">${num(geo.direccion || 0)} con dirección exacta</div></div>
      </div>
      <p class="sec">Archivos procesados: ${(r.archivos || []).map((a) => `${a.archivo} (${TIPOS[a.tipo] || a.tipo}, ${num(a.filas)} filas)`).join(' · ')}</p>
      ${r.cedulas_en_revision ? html`<p><a class="btn" href="/calidad" data-ruta>Revisar ${num(r.cedulas_en_revision)} coincidencias</a></p>` : ''}`);
      aviso('Importación terminada');
      refrescarInsignias();
      // El historial se vuelve a pedir para que muestre esta importación
      try { montar($('#historial', el), tablaHistorial(await api.get('/api/importaciones'))); } catch { /* se ve al volver a la vista */ }
    } catch (e) {
      montar($('#resultado', el), html`<div class="aviso-legal">${e.message}</div>`);
    } finally {
      $('#subir', el).disabled = false;
    }
  });
  $('#exportar', el).addEventListener('click', async () => {
    try { await descargar('/api/exportar.xlsx'); aviso('Exportación lista'); } catch (e) { aviso(e.message, 'error'); }
  });
}
