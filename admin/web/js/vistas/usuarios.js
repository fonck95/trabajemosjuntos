// Usuarios (7.8, solo el administrador): planilleros y consultores, sus indicadores, alertas y asignación.
import { html, montar } from '../ui.js';

export async function vistaUsuarios(el) {
  montar(el, html`<div class="vacio"><b>Usuarios</b>Esta sección todavía no está disponible.</div>`);
}

/** Detalle de un usuario (/usuarios/:id). */
export async function vistaUsuario(el) {
  montar(el, html`<div class="vacio"><b>Usuario</b>Esta sección todavía no está disponible.</div>`);
}
