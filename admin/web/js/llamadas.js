// Llamadas sin registrar (7.0): al tocar Llamar o WhatsApp se guarda solo {pid, indice, canal, t} en sessionStorage,
// sin número ni nombre. Al volver a la pestaña (también recargándola) y mientras haya una de menos de 2 h, una franja
// fija «Llamada sin registrar [Registrar]» abre el diálogo de acercamiento (7.5) con el canal y el número ya puestos.
import { api, ErrorApi } from './api.js';
import { avisoError, html, icono } from './ui.js';

const CLAVE = 'yj_llamada';
const VIGENCIA_MS = 2 * 3600 * 1000;
const CANALES = { llamada: 'Llamada', whatsapp: 'Mensaje de WhatsApp', sms: 'SMS' };

/** La llamada pendiente {pid, indice, canal, t} de menos de 2 h, o null. */
export function llamadaPendiente() {
  try {
    const l = JSON.parse(sessionStorage.getItem(CLAVE) || 'null');
    if (!l || !Number.isInteger(l.pid) || Date.now() - Number(l.t) > VIGENCIA_MS) {
      if (l) sessionStorage.removeItem(CLAVE);
      return null;
    }
    return l;
  } catch {
    return null;
  }
}

/** Anota la llamada o el mensaje que se acaba de iniciar: persona, índice del número usable y canal. */
export function marcarLlamada({ pid, indice = 0, canal = 'llamada' } = {}) {
  const id = Number(pid);
  if (!Number.isInteger(id)) return;
  try {
    sessionStorage.setItem(CLAVE, JSON.stringify({ pid: id, indice: Number(indice) || 0, canal, t: Date.now() }));
  } catch { /* almacenamiento bloqueado: no hay franja, pero la llamada sigue */ }
}

/** Olvida la llamada pendiente (al registrarla, al descartarla o al cerrar sesión). */
export function olvidarLlamada() {
  try { sessionStorage.removeItem(CLAVE); } catch { /* nada */ }
  document.getElementById('franja-llamada')?.remove();
}

let abriendo = false;
async function registrar(l) {
  if (abriendo) return;
  abriendo = true;
  try {
    const [{ dialogoAcercamiento }, p] = await Promise.all([
      import('./vistas/acercamiento.js'),
      api.get(`/api/personas/${l.pid}`),
    ]);
    const hecho = await dialogoAcercamiento(p, { canal: l.canal, indice: l.indice });
    if (hecho) olvidarLlamada();
  } catch (e) {
    // La ficha ya no está a su alcance (pasaron los 20 minutos de la cola y otro la tomó) o se unió con otra
    if (e instanceof ErrorApi && [403, 404, 409].includes(e.estado)) {
      avisoError(new ErrorApi(e.estado, `${e.message}. Si la llamada sí ocurrió, búsquela en «Mi trabajo» › Hoy o pida ayuda al administrador.`), 9000);
    } else avisoError(e);
  } finally {
    abriendo = false;
  }
}

/** Revisa si quedó una llamada sin registrar y muestra la franja. app.js la llama al cargar cada vista. */
export function revisarLlamadasPendientes() {
  const l = llamadaPendiente();
  let franja = document.getElementById('franja-llamada');
  if (!l) { franja?.remove(); return; }
  // Sin sesión (pantalla de ingreso) no hay franja
  if (!document.getElementById('app')) return;
  if (!franja) {
    franja = document.createElement('div');
    franja.id = 'franja-llamada';
    franja.className = 'franja-pendiente';
    franja.setAttribute('role', 'status');
    document.body.append(franja);
    franja.addEventListener('click', (e) => {
      const actual = llamadaPendiente();
      if (!actual) { franja.remove(); return; }
      if (e.target.closest('[data-registrar]')) registrar(actual);
      else if (e.target.closest('[data-descartar]')) olvidarLlamada();
    });
  }
  const minutos = Math.max(0, Math.round((Date.now() - l.t) / 60000));
  franja.innerHTML = String(html`${icono('telefono')}<span><b>${l.canal === 'llamada' ? 'Llamada sin registrar' : `${CANALES[l.canal] || 'Contacto'} sin registrar`}</b>
    <small>hace ${minutos < 1 ? 'menos de un minuto' : minutos === 1 ? '1 minuto' : `${minutos} minutos`}</small></span>
    <button class="btn chico primario" data-registrar>Registrar</button>
    <button class="btn chico fantasma" data-descartar aria-label="Descartar: no hubo llamada">✕</button>`);
}

// Volver del marcador o de WhatsApp: la pestaña vuelve a verse (o el navegador la restaura de su caché)
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') revisarLlamadasPendientes(); });
window.addEventListener('pageshow', () => revisarLlamadasPendientes());
