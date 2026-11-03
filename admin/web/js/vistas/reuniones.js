// Agenda de reuniones con el número de asistentes y personas nuevas que deja cada una.
import { api } from '../api.js';
import { $, aviso, datosForm, dialogo, hoy, html, icono, montar, num, titulo } from '../ui.js';
import { elegirPunto, opcionesLugares } from './comunes.js';

const MES = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];

export async function vistaReuniones(el, { ir }) {
  const [lista, cat] = await Promise.all([api.get('/api/reuniones'), api.get('/api/catalogos')]);
  const total = lista.reduce((a, r) => a + r.asistentes, 0);
  montar(el, html`
    <div class="cabecera">
      <div><h1>Reuniones</h1><div class="sub">${num(lista.length)} reuniones · ${num(total)} asistencias registradas</div></div>
      <div class="acciones"><button class="btn primario" id="nueva">${icono('mas')} Nueva reunión</button></div>
    </div>
    ${lista.length ? html`<div class="reuniones">${lista.map((r) => {
      const [a, m, d] = r.fecha.split('-');
      return html`<a class="tarjeta reunion-t" href="/reuniones/${r.id}" data-ruta>
        <div style="display:flex;gap:14px;align-items:center"><div class="fecha-bloque"><b>${+d}</b><small>${MES[+m - 1]} ${a.slice(2)}</small></div>
          <div style="min-width:0"><b style="font-size:16px">${r.titulo}</b><div class="sec">${titulo(r.lugar || 'Sin lugar')}${r.hora ? ' · ' + r.hora : ''}</div></div></div>
        ${r.tema ? html`<span class="chip borde" style="align-self:flex-start">${r.tema}</span>` : ''}
        <div style="display:flex;gap:18px;font-size:13.5px"><span><b style="font-size:20px">${num(r.asistentes)}</b> asistentes</span><span><b style="font-size:20px">${num(r.nuevos)}</b> nuevas en la base</span></div>
      </a>`;
    })}</div>` : html`<div class="tarjeta vacio"><b>Aún no hay reuniones</b><p>Cree una reunión y registre a los asistentes: cada asistencia actualiza el perfil de la persona y suma al mapa.</p></div>`}`);

  $('#nueva').addEventListener('click', () => {
    let punto = null;
    const { el: d, cerrar } = dialogo({
      titulo: 'Nueva reunión',
      cuerpo: html`<form class="form" id="f-reunion">
        <label class="campo ancho"><span>Título *</span><input name="titulo" required minlength="3" placeholder="Reunión con la JAC de Villa María"></label>
        <label class="campo"><span>Fecha *</span><input name="fecha" type="date" required value="${hoy()}"></label>
        <label class="campo"><span>Hora</span><input name="hora" type="time"></label>
        <label class="campo"><span>Barrio / vereda</span><select name="lugar_id">${opcionesLugares(cat)}</select></label>
        <label class="campo"><span>Sitio</span><input name="lugar_texto" placeholder="Caseta comunal"></label>
        <label class="campo ancho"><span>Tema</span><input name="tema" placeholder="Agua potable, vías, vivienda…"></label>
        <label class="campo ancho"><span>Descripción</span><textarea name="descripcion"></textarea></label>
        <div class="ancho"><button type="button" class="btn chico" id="punto">${icono('pin')} Marcar el sitio exacto en el mapa</button> <span class="sec" id="punto-t"></span></div>
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="crear">Crear y registrar asistentes</button>`,
    });
    $('#punto', d).addEventListener('click', async () => {
      punto = await elegirPunto({ titulo: 'Sitio de la reunión' });
      if (punto) $('#punto-t', d).textContent = `${punto[1].toFixed(5)}, ${punto[0].toFixed(5)}`;
    });
    $('#crear', d).addEventListener('click', async () => {
      const f = $('#f-reunion', d);
      if (!f.reportValidity()) return;
      const datos = datosForm(f);
      datos.lugar_id = datos.lugar_id ? Number(datos.lugar_id) : null;
      if (punto) { datos.lon = punto[0]; datos.lat = punto[1]; }
      try {
        const r = await api.post('/api/reuniones', datos);
        cerrar();
        aviso('Reunión creada');
        ir(`/reuniones/${r.id}`);
      } catch (e) { aviso(e.message, 'error'); }
    });
  });
}
