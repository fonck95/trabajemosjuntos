// Llamadas sin registrar (7.0): al tocar Llamar o WhatsApp se guarda solo {pid, indice, canal, t} en sessionStorage,
// sin número ni nombre, y mientras haya una de menos de 2 h una franja fija ofrece registrarla. Todavía no hace nada.

/** Revisa si quedó una llamada sin registrar y muestra la franja. app.js la llama al cargar cada vista. */
export function revisarLlamadasPendientes() {}

/** Anota la llamada o el mensaje que se acaba de iniciar: persona, índice del número usable y canal. */
export function marcarLlamada({ pid, indice, canal } = {}) {}

/** La llamada pendiente {pid, indice, canal, t} de menos de 2 h, o null. */
export function llamadaPendiente() {
  return null;
}

/** Olvida la llamada pendiente (al registrarla, al descartarla o al cerrar sesión). */
export function olvidarLlamada() {}
