// Agenda de reuniones (7.13) con el número de asistentes y personas nuevas que deja cada una. El planillero ve las
// suyas y las abiertas al equipo; de las demás, solo cuántas hay. El administrador y el coordinador deciden si una
// reunión queda abierta para que los planilleros registren asistentes.
import { api, puede, sesion } from '../api.js';
import { $, aviso, avisoError, datosForm, dialogo, hoy, html, icono, montar, num, titulo } from '../ui.js';
import { administra, elegirPunto, opcionesLugares } from './comunes.js';

const MES = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];

export async function vistaReuniones(el, { ir }) {
  const [resp, cat] = await Promise.all([api.get('/api/reuniones'), api.catalogos()]);
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const lista = Array.isArray(resp) ? resp : resp?.filas || resp?.reuniones || [];
  const ajenas = Array.isArray(resp) ? null : resp?.otras ?? resp?.ajenas ?? null;
  const total = lista.reduce((a, r) => a + (r.asistentes || 0), 0);
  const adm = administra();
  montar(el, html`
    <div class="cabecera">
      <div><h1>Reuniones</h1><div class="sub">${num(lista.length)} reuniones · ${num(total)} asistencias registradas${ajenas ? ` · ${num(ajenas)} de otros equipos` : ''}</div></div>
      ${puede('reuniones.crear') ? html`<div class="acciones"><button class="btn primario" id="nueva">${icono('mas')} Nueva reunión</button></div>` : ''}
    </div>
    ${lista.length ? html`<div class="reuniones">${lista.map((r) => {
      const [a, m, d] = String(r.fecha || '').split('-');
      const propia = r.creado_por_uid != null && r.creado_por_uid === sesion.uid;
      return html`<a class="tarjeta reunion-t" href="/reuniones/${r.id}" data-ruta>
        <div style="display:flex;gap:14px;align-items:center"><div class="fecha-bloque"><b>${+d || ''}</b><small>${MES[+m - 1] || ''} ${(a || '').slice(2)}</small></div>
          <div style="min-width:0"><b style="font-size:16px">${r.titulo}</b><div class="sec">${titulo(r.lugar || 'Sin lugar')}${r.hora ? ' · ' + r.hora : ''}</div></div></div>
        <div class="chips">${r.tema ? html`<span class="chip borde">${r.tema}</span>` : ''}${r.abierta_a_equipo ? html`<span class="chip azul">Abierta al equipo</span>` : ''}${propia && !adm ? html`<span class="chip verde">Suya</span>` : ''}</div>
        <div style="display:flex;gap:18px;font-size:13.5px"><span><b style="font-size:20px">${num(r.asistentes)}</b> asistentes</span><span title="Personas que se registraron en la base por primera vez en esta reunión"><b style="font-size:20px">${num(r.nuevos)}</b> nuevas en la base</span></div>
      </a>`;
    })}</div>` : html`<div class="tarjeta vacio"><b>Aún no hay reuniones${ajenas ? ' suyas' : ''}</b><p>Cree una reunión y registre a los asistentes: cada asistencia actualiza el perfil de la persona y suma al mapa.</p></div>`}
    ${ajenas ? html`<p class="sec" style="margin-top:14px">Hay ${num(ajenas)} reuniones de otros equipos que no están abiertas para registrar asistentes.</p>` : ''}`);

  $('#nueva', el)?.addEventListener('click', () => {
    let punto = null;
    const { el: d, cerrar } = dialogo({
      titulo: 'Nueva reunión',
      cuerpo: html`<form class="form" id="f-reunion">
        <label class="campo ancho"><span>Título *</span><input name="titulo" required minlength="3" maxlength="160" placeholder="Reunión con la JAC de Villa María"></label>
        <label class="campo"><span>Fecha *</span><input name="fecha" type="date" required value="${hoy()}"></label>
        <label class="campo"><span>Hora</span><input name="hora" type="time"></label>
        <label class="campo"><span>Barrio / vereda</span><select name="lugar_id">${opcionesLugares(cat)}</select></label>
        <label class="campo"><span>Sitio</span><input name="lugar_texto" maxlength="160" placeholder="Caseta comunal"></label>
        <label class="campo ancho"><span>Tema</span><input name="tema" maxlength="160" placeholder="Agua potable, vías, vivienda…"></label>
        <label class="campo ancho"><span>Descripción</span><textarea name="descripcion" maxlength="4000"></textarea></label>
        ${adm ? html`<label class="casilla ancho"><input type="checkbox" name="abierta_a_equipo"> Permitir que planilleros registren asistentes</label>` : ''}
        <div class="ancho"><button type="button" class="btn chico" id="punto">${icono('pin')} Marcar el sitio exacto en el mapa</button> <span class="sec" id="punto-t"></span></div>
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="crear">Crear y registrar asistentes</button>`,
    });
    $('#punto', d).addEventListener('click', async () => {
      punto = await elegirPunto({ titulo: 'Sitio de la reunión' });
      if (punto) $('#punto-t', d).textContent = `${punto[1].toFixed(5)}, ${punto[0].toFixed(5)}`;
    });
    $('#crear', d).addEventListener('click', async (ev) => {
      const f = $('#f-reunion', d);
      const boton = ev.currentTarget;
      // Un doble clic no debe crear dos reuniones
      if (boton.disabled || !f.reportValidity()) return;
      const datos = datosForm(f);
      datos.lugar_id = datos.lugar_id ? Number(datos.lugar_id) : null;
      if (!adm) delete datos.abierta_a_equipo;
      if (punto) { datos.lon = punto[0]; datos.lat = punto[1]; }
      boton.disabled = true;
      try {
        const r = await api.post('/api/reuniones', datos);
        cerrar();
        aviso('Reunión creada');
        ir(`/reuniones/${r.id}`);
      } catch (e) { avisoError(e); boton.disabled = false; }
    });
  });
}
