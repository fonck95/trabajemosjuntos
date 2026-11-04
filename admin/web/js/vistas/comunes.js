// Piezas compartidas entre vistas: alta rápida de personas y selector de ubicación en el mapa.
import { api, ErrorApi } from '../api.js';
import { BASES, CASCO, baseSegunTema, cargarMapLibre, dentroDeYondo } from '../mapa3d.js';
import { $, aviso, datosForm, dialogo, hoy, html, titulo } from '../ui.js';

export function opcionesLugares(cat, valor) {
  const grupos = { barrio: 'Barrios del casco', sector: 'Sectores', centro_poblado: 'Centros poblados', corregimiento: 'Corregimientos', caserio: 'Caseríos', vereda: 'Veredas' };
  return html`<option value="">Sin definir</option>${Object.entries(grupos).map(([t, g]) => {
    const ls = cat.lugares.filter((l) => l.tipo === t);
    return ls.length ? html`<optgroup label="${g}">${ls.map((l) => html`<option value="${l.id}" ${String(valor) === String(l.id) ? 'selected' : ''}>${titulo(l.nombre)}</option>`)}</optgroup>` : '';
  })}`;
}

/** Alta de una persona con verificación de duplicados. `reunionId` la registra además como asistente. */
export function formularioNuevaPersona({ cat, reunionId = null, nombreInicial = '', alCrear }) {
  const necesidades = cat.etiquetas.filter((e) => e.grupo === 'necesidad');
  const { el, cerrar } = dialogo({
    titulo: reunionId ? 'Registrar asistente nuevo' : 'Nueva persona',
    cuerpo: html`<form class="form" id="f-nueva">
      <label class="campo ancho"><span>Nombre completo *</span><input name="nombre" required minlength="3" value="${nombreInicial}"></label>
      <label class="campo"><span>Cédula</span><input name="cedula" inputmode="numeric"></label>
      <label class="campo"><span>Celular</span><input name="telefono" inputmode="tel"></label>
      <label class="campo"><span>Barrio / vereda</span><select name="lugar_id">${opcionesLugares(cat)}</select></label>
      <label class="campo"><span>Dirección</span><input name="direccion" placeholder="CL 49 # 45-12"></label>
      <label class="campo"><span>Sexo</span><select name="sexo"><option value="">—</option><option value="F">Mujer</option><option value="M">Hombre</option></select></label>
      <label class="campo"><span>Edad</span><input name="edad" type="number" min="0" max="120"></label>
      <label class="campo"><span>Autorización de datos</span><select name="consentimiento"><option value="pendiente">Pendiente</option><option value="si">Sí, autorizó</option><option value="no">No autorizó</option></select></label>
      <div class="campo ancho"><span>Necesidades</span><div class="chips">${necesidades.map((e) => html`<button type="button" class="chip" data-et="${e.id}" aria-pressed="false">${e.nombre}</button>`)}</div></div>
      <div class="ancho" id="parecidas"></div>
    </form>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="guardar">Guardar</button>`,
  });
  const form = $('#f-nueva', el);
  form.addEventListener('click', (e) => { const c = e.target.closest('[data-et]'); if (c) c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') !== 'true'); });
  let forzar = false, enCurso = false;
  const boton = $('#guardar', el);
  async function guardar() {
    // Un doble clic (o Enter y clic) no debe crear dos fichas: una sola petición a la vez
    if (enCurso || !form.reportValidity()) return;
    const d = datosForm(form);
    d.lugar_id = d.lugar_id ? Number(d.lugar_id) : null;
    d.etiquetas = [...form.querySelectorAll('[data-et][aria-pressed="true"]')].map((b) => Number(b.dataset.et));
    if (d.consentimiento === 'si') d.consentimiento_fecha = hoy(); // fecha local, no la de UTC
    enCurso = true;
    boton.disabled = true;
    try {
      const p = await api.post('/api/personas', { ...d, forzar, reunion_id: reunionId });
      cerrar();
      aviso(`${p.nombre} quedó registrada`);
      alCrear?.(p);
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 409 && e.detalle?.parecidas) {
        forzar = true;
        $('#parecidas', el).innerHTML = String(html`<div class="aviso-legal"><b>¿Es alguna de estas personas?</b> Si es así, elíjala para no duplicarla.
          <div class="resultados">${e.detalle.parecidas.map((p) => html`<div class="resultado"><div class="q"><b>${p.nombre}</b><small>${p.cedula || 'sin cédula'} · ${p.telefono || 'sin teléfono'} · ${titulo(p.lugar || '')}</small></div>
            <button type="button" class="btn chico" data-elegir="${p.id}">Es esta</button></div>`)}</div>
          <p class="sec">Si es otra persona, pulse Guardar de nuevo.</p></div>`);
        $('#parecidas', el).addEventListener('click', (ev) => {
          const b = ev.target.closest('[data-elegir]');
          if (b) { cerrar(); alCrear?.({ id: Number(b.dataset.elegir), existente: true }); }
        });
      } else aviso(e.message, 'error');
    } finally {
      enCurso = false;
      boton.disabled = false;
    }
  }
  boton.addEventListener('click', guardar);
  form.addEventListener('submit', (e) => { e.preventDefault(); guardar(); });
}

/** Diálogo con un mapa para elegir un punto. Resuelve [lon, lat] o null. */
export async function elegirPunto({ titulo: t = 'Ubicar en el mapa', inicial = null, ayuda = '' } = {}) {
  const maplibregl = await cargarMapLibre();
  const { el, cerrar, listo } = dialogo({
    titulo: t, ancho: true,
    cuerpo: html`<p class="sec" style="margin-top:0">${ayuda || 'Haga clic en el mapa o arrastre el marcador hasta el lugar exacto.'}</p>
      <div class="minimapa" style="height:min(60vh,520px)" id="elegir-mapa"></div>`,
    pie: html`<span class="sec" id="coord" style="margin-right:auto"></span><button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="usar">Usar este punto</button>`,
  });
  const map = new maplibregl.Map({ container: $('#elegir-mapa', el), style: BASES[baseSegunTema()],
    center: inicial || CASCO.center, zoom: inicial ? 16 : 14, attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  const marca = new maplibregl.Marker({ color: '#e3141b', draggable: true }).setLngLat(inicial || CASCO.center).addTo(map);
  // El servidor solo acepta puntos en Yondó y sus alrededores: fuera de ese rango no se deja elegir
  const mostrar = () => {
    const p = marca.getLngLat();
    const ok = dentroDeYondo(p.lng, p.lat);
    $('#coord', el).textContent = ok ? `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}` : 'Ese punto queda fuera de Yondó';
    $('#usar', el).disabled = !ok;
  };
  mostrar();
  marca.on('dragend', mostrar);
  map.on('click', (e) => { marca.setLngLat(e.lngLat); mostrar(); });
  let elegido = null;
  $('#usar', el).addEventListener('click', () => {
    const p = marca.getLngLat();
    if (!dentroDeYondo(p.lng, p.lat)) return;
    elegido = [p.lng, p.lat]; cerrar(elegido);
  });
  return listo.then(() => { map.remove(); return elegido; });
}
