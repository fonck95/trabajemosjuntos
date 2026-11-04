// Mi cuenta (7.9): cambio de clave, compromiso de confidencialidad e indicadores propios. Con la clave temporal o el
// compromiso pendientes, es la única vista que se abre. El coordinador cambia su clave y acepta el compromiso como
// planilleros y consultores; solo el administrador de `.env` (uid 0) no tiene clave en el panel.
import { api, configurar, nombreRol, puede, sesion } from '../api.js';
import { $, aviso, avisoError, fecha, html, montar } from '../ui.js';
import { pintarIndicadores } from './usuarios.js';

export async function vistaCuenta(el, { ir }) {
  const yo = await api.get('/api/yo');
  const admin = yo.rol === 'admin' && !yo.uid; // el administrador de `.env`
  // Si entró con algo pendiente, al ponerse al día vuelve a su inicio
  const pendienteAlEntrar = yo.debe_cambiar_clave || yo.compromiso_pendiente;

  function pintar() {
    const pendiente = yo.debe_cambiar_clave ? 'clave' : yo.compromiso_pendiente ? 'compromiso' : null;
    montar(el, html`
      <div class="cabecera"><div><h1>Mi cuenta</h1><div class="sub">${yo.nombre || yo.usuario} · ${nombreRol(yo.rol)}</div></div></div>
      ${pendiente === 'clave' ? html`<div class="aviso-cuenta" role="alert"><b>Cambie su clave temporal para continuar.</b> La clave que le dio el administrador sirve una sola vez.</div>` : ''}
      ${pendiente === 'compromiso' ? html`<div class="aviso-cuenta" role="alert"><b>Lea y acepte el compromiso de confidencialidad para continuar.</b></div>` : ''}
      <div class="rejilla r-12">
        <section class="tarjeta c-6" id="t-clave">
          <h2>Clave</h2>
          ${admin ? html`<p class="sec">La clave del administrador se cambia en Railway (variable <b>password</b>). Al cambiarla se cierran todas las sesiones.</p>` : html`
          <form id="f-clave" class="form-cuenta" novalidate>
            <label class="campo"><span>${yo.debe_cambiar_clave ? 'Clave temporal' : 'Clave actual'}</span><input name="actual" type="password" autocomplete="current-password" required></label>
            <label class="campo"><span>Clave nueva</span><input name="nueva" type="password" autocomplete="new-password" minlength="10" required></label>
            <label class="campo"><span>Repita la clave nueva</span><input name="repetida" type="password" autocomplete="new-password" minlength="10" required></label>
            <p class="sec">Al menos 10 caracteres, distinta de su usuario y difícil de adivinar. Una frase de tres o cuatro palabras sirve.</p>
            <div class="error" role="alert"></div>
            <div><button class="btn primario" type="submit">Cambiar clave</button></div>
          </form>`}
        </section>
        <section class="tarjeta c-6" id="t-compromiso">
          <h2>Compromiso de confidencialidad</h2>
          ${admin ? html`<p class="sec">El administrador responde por la base ante el titular. Los coordinadores, planilleros y consultores aceptan este compromiso antes de trabajar.</p>` : html`
          <ol class="compromiso">${(yo.compromiso?.puntos || []).map((p) => html`<li>${p}</li>`)}</ol>
          <p class="sec">Versión ${yo.compromiso?.version || '—'}${yo.compromiso?.aceptado ? html` · aceptado el ${fecha(yo.compromiso.aceptado_en, true)}` : ''}</p>
          ${yo.compromiso?.aceptado ? '' : html`<button class="btn primario" id="aceptar" ${yo.debe_cambiar_clave ? 'disabled title="Primero cambie su clave temporal"' : ''}>Acepto el compromiso</button>`}`}
        </section>
        <section class="tarjeta c-12" id="t-indicadores">
          <header><h2>Mis indicadores</h2><span class="nota">Últimos 30 días</span></header>
          <div id="indicadores">${pendiente ? html`<p class="sec">Aparecen cuando su cuenta esté al día.</p>` : html`<div class="cargando"><div class="giro"></div></div>`}</div>
        </section>
      </div>`);
    if (!pendiente) cargarIndicadores();
    if (pendiente === 'clave') el.querySelector('#f-clave [name=actual]')?.focus();
  }

  async function cargarIndicadores() {
    const c = $('#indicadores', el);
    try {
      const ind = await api.get('/api/yo/indicadores');
      if (c.isConnected) pintarIndicadores(c, ind, { rol: yo.rol });
    } catch (e) {
      if (c.isConnected) montar(c, html`<p class="sec">${e.message}</p>`);
    }
  }

  // Tras ponerse al día, la sesión queda como la ve el servidor y se va al inicio
  async function alDia() {
    const d = await api.get('/api/yo');
    Object.assign(yo, d);
    configurar({ token: d.csrf, usuario: d.usuario, uid: d.uid, rol: d.rol, permisos: d.permisos, excepto: d.excepto,
      nombre: d.nombre, debe_cambiar_clave: d.debe_cambiar_clave, compromiso_pendiente: d.compromiso_pendiente });
    if (!d.debe_cambiar_clave && !d.compromiso_pendiente && pendienteAlEntrar) {
      aviso('Su cuenta está al día');
      ir(puede('tablero.ver') ? '/' : '/trabajo');
      return;
    }
    pintar();
  }

  el.addEventListener('submit', async (e) => {
    if (e.target.id !== 'f-clave') return;
    e.preventDefault();
    const f = e.target;
    const error = f.querySelector('.error');
    error.textContent = '';
    if (f.nueva.value !== f.repetida.value) { error.textContent = 'Las dos claves nuevas no coinciden'; return; }
    const boton = f.querySelector('button[type=submit]');
    boton.disabled = true;
    try {
      const r = await api.post('/api/yo/clave', { actual: f.actual.value, nueva: f.nueva.value });
      // La sesión se renovó: el CSRF es otro
      configurar({ token: r.csrf, usuario: sesion.usuario, uid: sesion.uid, rol: sesion.rol, permisos: sesion.permisos,
        excepto: sesion.excepto, nombre: sesion.nombre, debe_cambiar_clave: false, compromiso_pendiente: sesion.compromisoPendiente });
      aviso('Clave cambiada');
      await alDia();
    } catch (err) {
      if (err?.estado === 401) return;
      error.textContent = err.message;
      f.actual.value = '';
      f.actual.focus();
    } finally {
      boton.disabled = false;
    }
  });
  el.addEventListener('click', async (e) => {
    if (!e.target.closest('#aceptar')) return;
    try {
      await api.post('/api/yo/compromiso', { version: yo.compromiso?.version });
      await alDia();
    } catch (err) { avisoError(err); }
  });
  pintar();
}
