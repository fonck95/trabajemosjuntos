// Trabajador (Web Worker de módulo) del motor sísmico: solo traduce los mensajes del 7.5 a llamadas de motor.js.
// Contrato de la torre, 7.5; data/sismo/ESQUEMA.md, «Mensajes del trabajador». Se crea desde la vista con
//   new Worker(new URL('../../sismo/trabajador.js', import.meta.url), { type: 'module' })
// y recibe URL absolutas. Los mensajes se atienden en orden (una cola). `analizar` corre de corrido: la vista cancela
// con worker.terminate(). La historia interna queda en el motor; solo se transfieren los búferes de cada respuesta.
import { crearMotor } from './motor.js';

const motor = crearMotor();
let cola = Promise.resolve();

/** Búferes de todos los arreglos tipados de un objeto (sin repetir), para transferirlos. */
function buferes(x, lista = [], vistos = new Set()) {
  if (!x || typeof x !== 'object') return lista;
  if (ArrayBuffer.isView(x)) {
    if (!vistos.has(x.buffer) && x.buffer.byteLength > 0) { vistos.add(x.buffer); lista.push(x.buffer); }
    return lista;
  }
  if (vistos.has(x)) return lista;
  vistos.add(x);
  for (const v of Array.isArray(x) ? x : Object.values(x)) buferes(v, lista, vistos);
  return lista;
}

const enviar = (msg) => self.postMessage(msg, buferes(msg));

async function atender(msg) {
  const id = msg.id;
  try {
    switch (msg.tipo) {
      case 'iniciar': {
        const listo = await motor.iniciar(msg);
        self.postMessage({ ...listo, tipo: 'listo', id });
        break;
      }
      case 'movimiento': {
        const r = await motor.movimiento(msg.params || {});
        enviar({ ...r, tipo: 'movimiento', id });
        break;
      }
      case 'analizar': {
        const alProgreso = (fraccion, t_s) => self.postMessage({ tipo: 'progreso', id, fraccion, t_s });
        const resultados = await motor.analizar(msg.params || {}, { ...(msg.opciones || {}), id }, alProgreso);
        enviar({ tipo: 'resultado', id, resultados });
        break;
      }
      case 'serie_elemento': {
        const s = motor.serieElemento(msg.elemento);
        enviar({ ...s, tipo: 'serie_elemento', id });
        break;
      }
      case 'cancelar':
        motor.cancelar();
        break;
      default: {
        const e = new Error(`mensaje desconocido: ${msg.tipo}`);
        e.codigo = 'datos';
        throw e;
      }
    }
  } catch (e) {
    const codigo = ['datos', 'no_converge', 'interno'].includes(e?.codigo) ? e.codigo : 'interno';
    const detalle = { ...(e?.detalle || {}) };
    if (e?.resultados) detalle.resultados = e.resultados;   // no_converge: resultados parciales
    if (codigo === 'interno' && e?.stack) detalle.pila = String(e.stack).split('\n').slice(0, 6).join('\n');
    enviar({ tipo: 'error', id, codigo, mensaje: e?.message || String(e), detalle });
  }
}

self.onmessage = (ev) => {
  const msg = ev.data || {};
  cola = cola.then(() => atender(msg));
  return cola;
};

self.postMessage({ tipo: 'cargado' });
