// Importación de los Excel (se procesan y se descartan; solo quedan los datos) y exportación de la base única.
import { api, descargar } from '../api.js';
import { refrescarInsignias } from '../app.js';
import { $, aviso, fecha, html, icono, montar, num } from '../ui.js';

export async function vistaImportar(el) {
  const historial = await api.get('/api/importaciones');
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
        ${historial.length ? html`<div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Fecha</th><th>Usuario</th><th>Archivos</th><th class="num">Personas nuevas</th><th class="num">Trámites nuevos</th><th class="num">Cédulas cruzadas</th><th class="num">Por revisar</th></tr></thead>
          <tbody>${historial.map((h) => html`<tr style="cursor:default"><td>${fecha(h.ts, true)}</td><td>${h.usuario}</td><td>${h.archivo}</td>
            <td class="num">${num(h.resumen.personas_nuevas)}</td><td class="num">${num(h.resumen.tramites_nuevos)}</td><td class="num">${num(h.resumen.cedulas_unidas_auto)}</td><td class="num">${num(h.resumen.cedulas_en_revision)}</td></tr>`)}</tbody></table></div>`
          : html`<p class="sec">Aún no se ha importado nada.</p>`}
      </section>
    </div>`);

  let archivos = [];
  const elegir = (lista) => {
    archivos = [...lista].filter((f) => f.name.toLowerCase().endsWith('.xlsx'));
    montar($('#elegidos'), html`${archivos.map((f) => html`<span class="chip azul">${f.name} · ${(f.size / 1048576).toFixed(1)} MB</span>`)}`);
    $('#subir').disabled = !archivos.length;
  };
  const zona = $('#zona');
  $('#archivos').addEventListener('change', (e) => elegir(e.target.files));
  zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('encima'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('encima'));
  zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('encima'); elegir(e.dataTransfer.files); });
  $('#subir').addEventListener('click', async () => {
    const fd = new FormData();
    archivos.forEach((f) => fd.append('archivos', f));
    $('#subir').disabled = true;
    montar($('#resultado'), html`<div style="display:flex;gap:10px;align-items:center"><div class="giro"></div><span>Leyendo, agrupando, cruzando por nombre y georreferenciando…</span></div>`);
    try {
      const r = await api.subir('/api/importar', fd);
      const geo = r.geo.por_precision || {};
      const ubicadas = Object.entries(geo).filter(([k]) => k !== 'sin_ubicar').reduce((a, [, v]) => a + v, 0);
      montar($('#resultado'), html`<div class="kpis" style="margin:0">
        <div class="kpi"><div class="t">Personas nuevas</div><div class="v">${num(r.personas_nuevas)}</div><div class="d">${num(r.personas_actualizadas)} actualizadas</div></div>
        <div class="kpi"><div class="t">Trámites nuevos</div><div class="v">${num(r.tramites_nuevos)}</div></div>
        <div class="kpi"><div class="t">Cédulas cruzadas</div><div class="v">${num(r.cedulas_unidas_auto)}</div><div class="d">${num(r.cedulas_en_revision)} por revisar · ${num(r.cedulas_sin_coincidencia)} sin par</div></div>
        <div class="kpi"><div class="t">Ubicadas</div><div class="v">${num(ubicadas)}</div><div class="d">${num(geo.direccion || 0)} con dirección exacta</div></div>
      </div>
      ${r.cedulas_en_revision ? html`<p><a class="btn" href="/calidad" data-ruta>Revisar ${num(r.cedulas_en_revision)} coincidencias</a></p>` : ''}`);
      aviso('Importación terminada');
      refrescarInsignias();
    } catch (e) {
      montar($('#resultado'), html`<div class="aviso-legal">${e.message}</div>`);
    } finally {
      $('#subir').disabled = false;
    }
  });
  $('#exportar').addEventListener('click', async () => {
    try { await descargar('/api/exportar.xlsx'); aviso('Exportación lista'); } catch (e) { aviso(e.message, 'error'); }
  });
}
