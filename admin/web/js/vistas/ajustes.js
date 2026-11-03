// Ajustes: campos propios para enriquecer los perfiles, catálogo de necesidades y registro de auditoría.
import { api } from '../api.js';
import { $, aviso, confirmar, fecha, html, montar, num } from '../ui.js';

const TIPOS = { texto: 'Texto', numero: 'Número', si_no: 'Sí / No', opcion: 'Lista de opciones', fecha: 'Fecha' };
const GRUPOS = { necesidad: 'Necesidades', interes: 'Grupos e intereses', rol: 'Roles' };

export async function vistaAjustes(el) {
  async function pintar() {
    const [cat, aud] = await Promise.all([api.get('/api/catalogos'), api.get('/api/auditoria')]);
    montar(el, html`
      <div class="cabecera"><div><h1>Ajustes</h1><div class="sub">Lo que se pregunta en cada reunión se vuelve un campo del perfil.</div></div></div>
      <div class="rejilla r-12">
        <section class="tarjeta c-6">
          <h2>Campos propios del perfil</h2>
          <p class="sec">Por ejemplo: «¿Tiene acueducto?», «Cultivo principal», «Tipo de vivienda». Aparecen en cada ficha y en la exportación.</p>
          <form id="f-campo" class="form" style="margin:12px 0">
            <label class="campo"><span>Nombre del campo</span><input name="etiqueta" required minlength="2" maxlength="60"></label>
            <label class="campo"><span>Tipo</span><select name="tipo">${Object.entries(TIPOS).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>
            <label class="campo ancho"><span>Opciones (si es lista, separadas por coma)</span><input name="opciones" placeholder="Propia, Arrendada, Familiar"></label>
            <div class="ancho"><button class="btn primario">Agregar campo</button></div>
          </form>
          <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Campo</th><th>Tipo</th><th>Estado</th><th></th></tr></thead><tbody>
            ${cat.campos.length ? cat.campos.map((c) => html`<tr style="cursor:default"><td><b>${c.etiqueta}</b>${c.opciones.length ? html`<div class="sec">${c.opciones.join(' · ')}</div>` : ''}</td>
              <td>${TIPOS[c.tipo]}</td><td>${c.activo ? html`<span class="chip verde">Activo</span>` : html`<span class="chip">Oculto</span>`}</td>
              <td><button class="btn chico" data-campo="${c.id}" data-activo="${c.activo ? 0 : 1}">${c.activo ? 'Ocultar' : 'Mostrar'}</button></td></tr>`)
              : html`<tr><td colspan="4" class="sec">Aún no hay campos propios.</td></tr>`}
          </tbody></table></div>
        </section>
        <section class="tarjeta c-6">
          <h2>Necesidades, grupos y roles</h2>
          <form id="f-et" style="display:flex;gap:8px;margin:12px 0;flex-wrap:wrap">
            <input class="entrada" name="nombre" placeholder="Nueva etiqueta" required minlength="2" style="flex:1 1 180px">
            <select class="entrada" name="grupo" style="width:auto">${Object.entries(GRUPOS).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select>
            <button class="btn primario">Agregar</button>
          </form>
          ${Object.entries(GRUPOS).map(([g, t]) => html`<h3 style="font-size:13px;margin:16px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">${t}</h3>
            <div class="chips">${cat.etiquetas.filter((e) => e.grupo === g).map((e) => html`<span class="chip borde">${e.nombre} · ${num(e.n)} <button class="btn fantasma chico" style="padding:0 4px" data-borrar-et="${e.id}" aria-label="Borrar ${e.nombre}">✕</button></span>`)}</div>`)}
        </section>
        <section class="tarjeta c-12">
          <header><h2>Auditoría</h2><span class="nota">${num(aud.total)} acciones registradas (últimas 100)</span></header>
          <div class="envoltura-tabla" style="max-height:420px;overflow:auto"><table class="tabla"><thead><tr><th>Cuándo</th><th>Usuario</th><th>Acción</th><th>Sobre</th><th>IP</th></tr></thead>
            <tbody>${aud.filas.map((a) => html`<tr style="cursor:default"><td>${fecha(a.ts, true)}</td><td>${a.usuario || 'sistema'}</td><td>${a.accion.replace(/_/g, ' ')}</td>
              <td>${a.entidad === 'persona' ? html`<a href="/personas/${a.entidad_id}" data-ruta>persona ${a.entidad_id}</a>` : a.entidad ? `${a.entidad} ${a.entidad_id ?? ''}` : ''}</td><td class="sec">${a.ip || ''}</td></tr>`)}</tbody></table></div>
        </section>
        <section class="tarjeta c-12">
          <h2>Protección de datos personales</h2>
          <div class="aviso-legal">Esta base contiene datos personales y algunos sensibles (afiliación política, condición de víctima, salud). La Ley 1581 de 2012 exige autorización previa,
            expresa e informada del titular, informar la finalidad, y atender consultas, correcciones y supresiones. El campo «Autorización de datos» de cada ficha y la opción
            «Suprimir datos» existen para eso. Los datos de bases oficiales (como las del SISBÉN) solo pueden usarse para la finalidad con la que se recogieron.</div>
        </section>
      </div>`);
  }

  el.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      if (f.id === 'f-campo') {
        await api.post('/api/campos', { etiqueta: f.etiqueta.value, tipo: f.tipo.value, opciones: f.opciones.value.split(',').map((s) => s.trim()).filter(Boolean) });
        aviso('Campo agregado');
      } else if (f.id === 'f-et') {
        await api.post('/api/etiquetas', { nombre: f.nombre.value, grupo: f.grupo.value });
        aviso('Etiqueta agregada');
      }
      pintar();
    } catch (err) { aviso(err.message, 'error'); }
  });
  el.addEventListener('click', async (e) => {
    const c = e.target.closest('[data-campo]');
    if (c) { await api.patch(`/api/campos/${c.dataset.campo}`, { activo: c.dataset.activo === '1' }); pintar(); return; }
    const b = e.target.closest('[data-borrar-et]');
    if (b && await confirmar('¿Borrar esta etiqueta? Se quitará de todas las personas.', { si: 'Borrar', peligro: true })) {
      await api.del(`/api/etiquetas/${b.dataset.borrarEt}`); pintar();
    }
  });
  await pintar();
  void $;
}
