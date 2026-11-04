// Mi trabajo (7.7): listas del planillero, cola y persona actual del consultor, y los indicadores propios.
import { html, montar } from '../ui.js';

export async function vistaTrabajo(el) {
  montar(el, html`<div class="vacio"><b>Mi trabajo</b>Esta sección todavía no está disponible.</div>`);
}
